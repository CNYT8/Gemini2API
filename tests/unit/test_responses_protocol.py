from app.core.responses_protocol import parse_responses_input


def test_string_input_becomes_single_user_message():
    msgs = parse_responses_input("hello there")
    assert msgs == [{"role": "user", "content": "hello there"}]


def test_instructions_becomes_leading_system_message():
    msgs = parse_responses_input("hi", instructions="Be concise.")
    assert msgs[0] == {"role": "system", "content": "Be concise."}
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_array_input_message_item_with_input_text_parts():
    msgs = parse_responses_input([
        {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "describe this"},
        ]},
    ])
    assert msgs == [{"role": "user", "content": [{"type": "text", "text": "describe this"}]}]


def test_array_input_message_with_image_part_converted_to_openai_shape():
    msgs = parse_responses_input([
        {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "what is this"},
            {"type": "input_image", "image_url": "https://x.example/a.png"},
        ]},
    ])
    content = msgs[0]["content"]
    assert content[0] == {"type": "text", "text": "what is this"}
    assert content[1] == {"type": "image_url", "image_url": {"url": "https://x.example/a.png"}}


def test_bare_object_input_treated_as_single_item_list():
    msgs = parse_responses_input({"type": "message", "role": "user", "content": "hi"})
    assert msgs == [{"role": "user", "content": "hi"}]


def test_function_call_history_item_becomes_assistant_message():
    msgs = parse_responses_input([
        {"type": "function_call", "call_id": "call_abc", "name": "run_shell",
         "arguments": '{"cmd": "ls"}'},
    ])
    assert msgs == [{"role": "assistant",
                     "content": '(called tool run_shell with arguments {"cmd": "ls"})'}]


def test_function_call_output_item_becomes_tool_message():
    msgs = parse_responses_input([
        {"type": "function_call_output", "call_id": "call_abc", "output": "file1.txt\nfile2.txt"},
    ])
    assert msgs == [{"role": "tool", "content": "file1.txt\nfile2.txt"}]


def test_output_text_content_part_maps_to_text():
    msgs = parse_responses_input([
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "previous reply"},
        ]},
    ])
    assert msgs == [{"role": "assistant", "content": [{"type": "text", "text": "previous reply"}]}]


from app.core.responses_protocol import build_responses_object, new_response_id


def test_new_response_id_has_resp_prefix():
    rid = new_response_id()
    assert rid.startswith("resp_") and len(rid) > len("resp_")


def test_build_responses_object_basic_shape():
    output = [{"id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
               "content": [{"type": "output_text", "text": "hi", "annotations": []}]}]
    obj = build_responses_object(
        model="gemini-pro", status="completed", output=output,
        request_params={"tools": [], "tool_choice": "auto", "store": True},
        usage={"input_tokens": 3, "output_tokens": 2},
    )
    assert obj["object"] == "response"
    assert obj["id"].startswith("resp_")
    assert obj["status"] == "completed"
    assert obj["model"] == "gemini-pro"
    assert obj["output"] == output
    assert obj["tools"] == []
    assert obj["tool_choice"] == "auto"
    assert obj["store"] is True
    assert obj["usage"]["input_tokens"] == 3
    assert obj["usage"]["input_tokens_details"] == {"cached_tokens": 0}
    assert obj["usage"]["output_tokens_details"] == {"reasoning_tokens": 0}
    assert obj["usage"]["total_tokens"] == 5
    assert obj["error"] is None
    assert "created_at" in obj


def test_build_responses_object_omits_unset_request_params():
    obj = build_responses_object(model="gemini-pro", status="completed", output=[],
                                 request_params={}, usage={"input_tokens": 0, "output_tokens": 0})
    assert "tools" not in obj
    assert "tool_choice" not in obj
