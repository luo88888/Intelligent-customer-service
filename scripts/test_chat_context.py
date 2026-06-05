"""
测试 /v1/chat/completions 多轮对话上下文

验证修复后的接口能正确利用客户端传来的 messages 历史。
"""
import requests
import json


BASE_URL = "http://localhost:8000"


def test_context_awareness():
    """测试多轮对话：Agent 能否记住上一轮的对话内容"""
    print("=" * 60)
    print("测试多轮对话上下文")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "我叫小明，我有一台S1扫地机器人"},
        {"role": "assistant", "content": "你好小明！S1是一款很不错的扫地机器人，有什么可以帮你的吗？"},
        {"role": "user", "content": "我刚才说我叫什么名字？我用的什么型号？"}
    ]

    payload = {
        "model": "smart-sweep-agent",
        "messages": messages,
        "stream": False
    }

    resp = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload)
    data = resp.json()

    print(f"\n对话历史（发送给服务端）：")
    for m in messages:
        print(f"  [{m['role']}] {m['content']}")

    choices = data.get("choices", [])
    if choices:
        reply = choices[0].get("message", {}).get("content", "")
        print(f"\nAgent 回复：\n{reply}")
        print(f"\n--- 验证 ---")
        # 检查 Agent 是否引用了历史中的信息
        if "小明" in reply and "S1" in reply:
            print("✅ Agent 正确记住了用户名和型号（多轮上下文生效）")
        elif "小明" in reply:
            print("⚠️ Agent 只记住了用户名，没有提及型号")
        elif "S1" in reply:
            print("⚠️ Agent 只记住了型号，没有提及用户名")
        else:
            print("❌ Agent 没有利用历史上下文（可能仍然取最后一条消息）")
    else:
        print("❌ 没有收到回复")


def test_no_cross_contamination():
    """测试请求之间是否隔离（无上下文污染）"""
    print("\n" + "=" * 60)
    print("测试请求隔离（无跨请求污染）")
    print("=" * 60)

    # 请求 1：用户 A 的对话
    payload_a = {
        "model": "smart-sweep-agent",
        "messages": [
            {"role": "user", "content": "我是用户A，记住我的名字"},
            {"role": "assistant", "content": "好的用户A！"},
            {"role": "user", "content": "重复我的名字"}
        ],
        "stream": False
    }
    resp_a = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload_a)
    reply_a = resp_a.json()["choices"][0]["message"]["content"]
    print(f"\n请求A回复: {reply_a[:100]}...")

    # 请求 2：用户 B 的对话（不应该知道用户 A）
    payload_b = {
        "model": "smart-sweep-agent",
        "messages": [
            {"role": "user", "content": "我叫什么名字？"}
        ],
        "stream": False
    }
    resp_b = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload_b)
    reply_b = resp_b.json()["choices"][0]["message"]["content"]
    print(f"请求B回复: {reply_b[:100]}...")

    # 如果请求隔离正常，B 不应该知道 "用户A"
    if "用户A" not in reply_b and "用户B" not in reply_b:
        print("\n✅ 请求间上下文隔离正常（B 不知道 A 的信息）")
    elif "用户A" in reply_b:
        print("\n❌ 请求间存在上下文泄漏！B 知道了 A 的名字")
    else:
        print("\n⚠️ 无法确定")


if __name__ == "__main__":
    test_context_awareness()
    test_no_cross_contamination()
