## ADDED Requirements

### Requirement: URL-fetching tools validate their target before connecting

The `read_url` and `read_rss_feed` tools SHALL validate a URL before fetching it, and SHALL refuse any URL that does not pass.

Validation SHALL require an `http` or `https` scheme, and SHALL reject any URL whose hostname resolves to loopback, link-local, private, or otherwise non-routable address space. Validation SHALL be applied to the **resolved addresses**, not to the hostname string: a name such as `localtest.me` resolves to loopback while looking public, so a literal-only check does not hold.

Redirects SHALL be followed only after re-validating each hop. A permitted public URL that redirects to `169.254.169.254` must not be followed.

These tools are invoked by the task LLM, which routinely acts on content fetched from the internet. The realistic threat is not a human choosing a hostile URL but the agent being induced to fetch one, so refusal must not depend on the caller's judgement.

A refused URL SHALL return an error identifying why, and SHALL NOT return any fetched content.

#### Scenario: Loopback address refused

- **WHEN** a tool is called with `http://127.0.0.1:9090/metrics`
- **THEN** the fetch is refused and no content is returned

#### Scenario: Cloud metadata endpoint refused

- **WHEN** a tool is called with `http://169.254.169.254/latest/meta-data/`
- **THEN** the fetch is refused and no content is returned

#### Scenario: Public hostname resolving to loopback refused

- **WHEN** a tool is called with a public hostname that resolves to a loopback address
- **THEN** the fetch is refused, because validation applies to the resolved address rather than the hostname

#### Scenario: Redirect into private space refused

- **WHEN** a permitted public URL responds with a redirect to a private address
- **THEN** the redirect is not followed and no content is returned

#### Scenario: Non-HTTP scheme refused

- **WHEN** a tool is called with a `file://` URL
- **THEN** the fetch is refused

#### Scenario: Ordinary public URL still works

- **WHEN** a tool is called with an ordinary public `https` URL
- **THEN** the content is fetched and returned as before

### Requirement: Internal fetch targets require an explicit allowlist

The backend SHALL support an allowlist of hosts exempt from the private-address restriction. The allowlist SHALL be empty by default.

Some deployments legitimately fetch internal hosts — an internal wiki or feed. Without a supported way to permit those, the restriction will be removed wholesale the first time it blocks something real, losing the protection entirely. An explicit, empty-by-default allowlist keeps the safe default while making each exception deliberate and visible.

#### Scenario: Allowlisted internal host permitted

- **WHEN** an internal host is in the allowlist and a tool is called with a URL on that host
- **THEN** the fetch proceeds despite resolving to private address space

#### Scenario: Non-allowlisted internal host still refused

- **WHEN** a tool is called with a URL on an internal host that is not in the allowlist
- **THEN** the fetch is refused

#### Scenario: Default configuration allows no internal hosts

- **WHEN** no allowlist has been configured
- **THEN** every private, loopback and link-local target is refused
