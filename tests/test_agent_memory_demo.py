from demo.demo_agent_memory_justified_answer import run_demo


def test_justified_answer_demo_writes_and_explains_chain(tmp_path):
    result = run_demo(data_dir=str(tmp_path / "memory"), print_output=False)

    entries = result["entries"]
    facts = entries["facts"]
    hypothesis = entries["hypothesis"]
    inference = entries["inference"]
    decision = entries["decision"]

    assert len(facts) >= 1
    assert hypothesis.hash
    assert inference.hash
    assert decision.hash

    inference_depends = set(result["explanation"]["dependency_map"][inference.hash][i]["entry_hash"] for i in range(3))
    expected_inference_refs = {facts[0].hash, facts[1].hash, hypothesis.hash}
    assert inference_depends == expected_inference_refs

    decision_dependencies = result["explanation"]["dependencies"]
    assert [item["entry_hash"] for item in decision_dependencies] == [inference.hash]

    decision_record = result["explanation"]["decision"]
    assert decision_record["kind"] == "decision"
    assert decision_record["entry_hash"] == decision.hash

    supporting_hashes = {item["entry_hash"] for item in result["explanation"]["supporting_entries"]}
    assert expected_inference_refs.issubset(supporting_hashes)
    assert inference.hash in supporting_hashes
    assert all(value for value in supporting_hashes)

    output = result["output"]
    assert result["question"] in output
    assert decision.hash in output
    assert inference.hash in output
    assert "DSM currently provides tamper-evidence in local trust" in output
