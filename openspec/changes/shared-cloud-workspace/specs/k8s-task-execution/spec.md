## ADDED Requirements

### Requirement: Task Jobs mount the workspace over native NFS

When a task's mount specification includes a shared workspace, `KubernetesRuntime` SHALL mount the gateway over NFS targeting the gateway's static ClusterIP (not a DNS name, since kubelet performs the mount from the node network where cluster DNS is unavailable), mounted read-write at the container path. Because pod-inline `nfs:` volumes cannot carry mount options (spike finding F7), the required NFSv3 options — including `nolock` (no NLM support in the gateway) and `soft` with conservative timeouts, so a dead gateway produces I/O errors in the task rather than an unkillable hung pod — SHALL be expressed on a **PersistentVolume** (static, CSI-free) whose PVC the Job binds, or via a StorageClass `mountOptions`. No CSI driver SHALL be required.

Conservative timeouts are required because the spike observed that aggressive `soft` timeouts (`timeo=30,retrans=2`) cause the *first* cold directory access to fail with an I/O error while rclone populates the VFS from the cloud; the mount options SHALL allow enough time for a cold cloud listing to complete.

#### Scenario: Mount options applied via PersistentVolume

- **WHEN** a workspace mount is added to a task Job
- **THEN** the `vers=3,nolock,soft` (and timeout) options are carried on a PersistentVolume / StorageClass, not an inline pod `nfs:` volume, so they actually take effect

### Requirement: Nodes require an NFS client for workspace mounts

Task Jobs mount the gateway via the kubelet, which shells out to the host `mount.nfs` helper. Therefore every node that can schedule task Jobs SHALL have an NFS client (`nfs-utils` or equivalent) installed; the `nfs` kernel module alone is insufficient (spike finding F2). This SHALL be documented as a cluster prerequisite for enabling the workspace.

#### Scenario: Node without NFS client

- **WHEN** a workspace-enabled task Job is scheduled to a node lacking `mount.nfs`
- **THEN** the mount fails and the failure is surfaced (task error / event), rather than the feature silently misbehaving — and the prerequisite is documented so operators can remediate

#### Scenario: Workspace-enabled task Job

- **WHEN** a task with a workspace mount runs on Kubernetes
- **THEN** the Job pod contains an `nfs` volume pointing at the gateway ClusterIP with the profile's subpath, mounted at `/shared`

#### Scenario: Gateway down mid-task

- **WHEN** the gateway becomes unreachable while a task pod holds the mount
- **THEN** file operations on `/shared` fail with I/O errors after the soft-mount timeout and the pod remains schedulable/terminable

#### Scenario: Non-workspace task unaffected

- **WHEN** a task without workspace enablement runs on Kubernetes
- **THEN** the Job spec contains no NFS volume and is identical to pre-workspace behavior
