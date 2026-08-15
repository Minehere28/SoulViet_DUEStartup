from agent.memory import AgentMemory


def test_long_term_memory_is_namespaced_and_retrievable(tmp_path):
    memory = AgentMemory(tmp_path)
    saved = memory.save("user-a", "Tôi thích hải sản địa phương")
    memory.save("user-b", "Tôi thích bảo tàng")

    results = memory.search("user-a", "ăn hải sản", limit=5)

    assert [item["id"] for item in results] == [saved["id"]]
    assert "hải sản" in results[0]["text"]
    assert memory.search("user-c", "hải sản") == []


def test_memory_can_be_forgotten(tmp_path):
    memory = AgentMemory(tmp_path)
    saved = memory.save("user-a", "Không thích quán chuỗi")

    memory.forget("user-a", saved["id"])

    assert memory.list("user-a") == []
