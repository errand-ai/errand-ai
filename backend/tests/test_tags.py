from httpx import AsyncClient


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


# --- GET /api/tags ---


async def test_tags_empty(client: AsyncClient):
    """No tags exist initially."""
    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_tags_with_query(client: AsyncClient):
    """Tags created via task creation are searchable."""
    # Create a short-input task — it gets the "Needs Info" tag
    await create_task(client, "Fix bug")

    resp = await client.get("/api/tags", params={"q": "Needs"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Needs Info"


async def test_tags_query_case_insensitive(client: AsyncClient):
    """Tag prefix search is case-insensitive."""
    await create_task(client, "Fix bug")

    resp = await client.get("/api/tags", params={"q": "needs"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Needs Info"


async def test_tags_query_no_matches(client: AsyncClient):
    """Non-matching query returns empty list."""
    await create_task(client, "Fix bug")

    resp = await client.get("/api/tags", params={"q": "zzz"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_tags_without_query_returns_all(client: AsyncClient):
    """No query param returns all tags (up to limit)."""
    await create_task(client, "Fix bug")

    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Needs Info"


# --- PATCH /api/tasks/{id} with tags ---


async def test_patch_set_tags(client: AsyncClient):
    """Setting tags on a task creates and associates them."""
    task = await create_task(client, "Build app")
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"tags": ["urgent", "backend"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert sorted(data["tags"]) == ["backend", "urgent"]


async def test_patch_replace_tags(client: AsyncClient):
    """Setting tags replaces existing tags."""
    task = await create_task(client, "Build app")
    # Short input gets "Needs Info" tag automatically
    assert "Needs Info" in task["tags"]

    # Replace with new tags
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"tags": ["frontend"]}
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["frontend"]


async def test_patch_remove_all_tags(client: AsyncClient):
    """Setting tags to empty list removes all tags."""
    task = await create_task(client, "Build app")
    assert len(task["tags"]) > 0  # Has "Needs Info"

    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"tags": []}
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == []


async def test_patch_omit_tags_preserves_existing(client: AsyncClient):
    """Not including tags in PATCH preserves existing tags."""
    task = await create_task(client, "Build app")
    original_tags = task["tags"]

    # Patch only the title, no tags field
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"title": "Updated title"}
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == original_tags


async def test_patch_tags_creates_new_tags(client: AsyncClient):
    """Tags that don't exist are auto-created."""
    task = await create_task(client, "Build app")
    await client.patch(
        f"/api/tasks/{task['id']}", json={"tags": ["new-tag-alpha", "new-tag-beta"]}
    )

    # Verify tags are searchable
    resp = await client.get("/api/tags", params={"q": "new-tag"})
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "new-tag-alpha" in names
    assert "new-tag-beta" in names


async def test_tags_sorted_alphabetically_in_response(client: AsyncClient):
    """Tags in task response are sorted alphabetically."""
    task = await create_task(client, "Build app")
    resp = await client.patch(
        f"/api/tasks/{task['id']}", json={"tags": ["zebra", "apple", "mango"]}
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["apple", "mango", "zebra"]
