import json
from api.app import app


def test_agents_roster_and_parallel_dispatch():
    c = app.test_client()
    res = c.get('/api/agents/roster')
    assert res.status_code == 200
    roster = res.get_json()["data"]
    assert len(roster) == 5
    ids = [a["id"] for a in roster]
    assert "grandmaster" in ids
    assert "sentinel" in ids
    assert "principal" in ids
    assert "sensei" in ids
    assert "scout" in ids

    # Parallel All-Out Dispatch
    d_res = c.post('/api/agents/dispatch', json={
        "mission": "Brainstorm and investigate high-yield features",
        "all_out": True,
        "parallel": True,
    })
    assert d_res.status_code == 200
    data = d_res.get_json()["data"]
    assert data["is_all_out"] is True
    assert data["workers_count"] == 5
    assert len(data["stages"]) == 5
    # Verify stages have thread identifiers
    for stage in data["stages"]:
        assert "Parallel-Worker" in stage["thread_id"] or "Worker-Thread" in stage["thread_id"]

    # History
    h_res = c.get('/api/agents/history')
    assert h_res.status_code == 200
    history = h_res.get_json()["data"]
    assert len(history) >= 1


def test_speedrun_arena_flow():
    c = app.test_client()
    stats = c.get('/api/speedrun/stats').get_json()["data"]
    assert "total_sessions" in stats
    assert "current_combo" in stats

    # Complete a 25m speedrun
    comp = c.post('/api/speedrun/complete', json={"minutes": 25, "combo": 1.5})
    assert comp.status_code == 200
    data = comp.get_json()["data"]
    assert data["minutes"] == 25
    assert data["boss_damage"] == 50
    assert data["xp_earned"] >= 30

    # Distraction Parking Lot
    p_add = c.post('/api/speedrun/parking', json={"thought": "Check laundry"})
    assert p_add.status_code == 200
    thought_id = p_add.get_json()["data"]["id"]

    p_list = c.get('/api/speedrun/parking').get_json()["data"]
    assert any(t["id"] == thought_id for t in p_list)

    p_del = c.delete(f'/api/speedrun/parking/{thought_id}')
    assert p_del.status_code == 200


def test_bounties_and_gacha_flow():
    c = app.test_client()
    today = c.get('/api/bounties/today').get_json()["data"]
    bounties = today["bounties"]
    assert len(bounties) == 4
    tiers = [b["tier"] for b in bounties]
    assert "Bronze" in tiers
    assert "Silver" in tiers
    assert "Gold" in tiers
    assert "Legendary" in tiers

    # Claim a bounty
    b_id = bounties[0]["id"]
    claim = c.post('/api/bounties/claim', json={"bounty_id": b_id})
    assert claim.status_code == 200
    assert claim.get_json()["data"]["claimed"] is True

    # Pull Gacha
    pull = c.post('/api/bounties/gacha/pull')
    assert pull.status_code == 200
    p_data = pull.get_json()["data"]["pull"]
    assert "title" in p_data
    assert p_data["rarity"] in ("Common", "Rare", "Epic", "Legendary")


def test_code_duel_arena_flow():
    c = app.test_client()
    opps = c.get('/api/arena/opponents').get_json()["data"]
    assert len(opps) >= 4

    # Start match
    m_start = c.post('/api/arena/match/start', json={"bot_id": "rookie_bot"})
    assert m_start.status_code == 200
    m_data = m_start.get_json()["data"]
    questions = m_data["questions"]
    assert len(questions) == 5

    # Submit match answers
    answers = {q["id"]: 1 for q in questions}
    submit = c.post('/api/arena/match/submit', json={"bot_id": "rookie_bot", "answers": answers})
    assert submit.status_code == 200
    sub_data = submit.get_json()["data"]
    assert "player_score" in sub_data
    assert "bot_score" in sub_data
    assert "won" in sub_data
    assert sub_data["xp_awarded"] > 0

    stats = c.get('/api/arena/stats').get_json()["data"]
    assert stats["total_matches"] >= 1


def test_sm2_drillmaster_flow():
    c = app.test_client()
    deck = c.get('/api/drillmaster/deck').get_json()["data"]
    due = deck["due_cards"]
    assert len(due) >= 1

    card = due[0]
    # Grade 4 (Good)
    rev = c.post('/api/drillmaster/review', json={"card_id": card["id"], "grade": 4})
    assert rev.status_code == 200
    r_data = rev.get_json()["data"]
    assert r_data["card_id"] == card["id"]
    assert r_data["new_interval_days"] >= 1
    assert r_data["xp_awarded"] > 0

    # Add custom card
    add_c = c.post('/api/drillmaster/card', json={
        "front": "What is Amortized Analysis?",
        "back": "Average running time per operation over a worst-case sequence of operations.",
        "category": "Algorithms",
    })
    assert add_c.status_code == 200


def test_ghost_racer_flow():
    c = app.test_client()
    tracks_res = c.get('/api/ghost/tracks')
    assert tracks_res.status_code == 200
    tracks = tracks_res.get_json()["tracks"]
    assert len(tracks) >= 5

    # Run Binary Search race
    t = tracks[0]
    sub = c.post('/api/ghost/submit', json={
        "track_id": t["id"],
        "time_ms": 3200,
        "accuracy": 100.0,
    })
    assert sub.status_code == 200
    run = sub.get_json()["run"]
    assert run["track_id"] == t["id"]
    assert run["wpm"] > 0
    assert run["xp_earned"] > 0

    # Profile
    p_res = c.get('/api/ghost/profile')
    assert p_res.status_code == 200
    stats = p_res.get_json()["stats"]
    assert stats["total_races"] >= 1
    assert stats["ghost_elo"] >= 1200


def test_commit_forge_flow():
    c = app.test_client()
    inv_before = c.get('/api/forge/inventory').get_json()
    assert inv_before["status"] == "success"

    # Transmute code snippet
    code = """def quickselect(nums: list[int], k: int) -> int:
    pivot = nums[len(nums) // 2]
    left = [x for x in nums if x < pivot]
    mid = [x for x in nums if x == pivot]
    right = [x for x in nums if x > pivot]
    if k <= len(left):
        return quickselect(left, k)
    elif k <= len(left) + len(mid):
        return pivot
    return quickselect(right, k - len(left) - len(mid))"""

    t_res = c.post('/api/forge/transmute', json={
        "code": code,
        "name": "Blade of Quickselect",
        "slot": "Weapon",
    })
    assert t_res.status_code == 201
    art = t_res.get_json()["artifact"]
    assert art["name"] == "Blade of Quickselect"
    assert art["rarity"] in ("Common", "Rare", "Epic", "Legendary", "Mythic")
    assert art["power"] > 0

    # Upgrade
    u_res = c.post(f'/api/forge/upgrade/{art["id"]}')
    assert u_res.status_code == 200
    assert u_res.get_json()["artifact"]["level"] == 2
