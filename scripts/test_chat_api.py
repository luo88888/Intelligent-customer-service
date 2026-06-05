"""
测试 /v1/chat/completions 兼容接口

测试非流式和流式两种模式。
"""
import requests
import json


BASE_URL = "http://localhost:8000"


def test_non_stream():
    """测试非流式请求"""
    print("=" * 50)
    print("1. 测试非流式请求 (stream=false)")
    print("=" * 50)

    payload = {
        "model": "smart-sweep-agent",
        "messages": [
            {"role": "user", "content": "你好，扫地机器人S1的电池续航怎么样？"}
        ],
        "stream": False
    }

    resp = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload)
    data = resp.json()

    print(f"HTTP Status: {resp.status_code}")
    print(f"ID: {data.get('id', 'N/A')}")
    print(f"Model: {data.get('model', 'N/A')}")

    choices = data.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        print(f"\n回复内容: {content[:500]}...")
        print(f"\n完整回复长度: {len(content)} 字符")

    rag_docs = data.get("rag_docs")
    if rag_docs:
        print(f"\nRAG 参考资料: {len(rag_docs)} 组")
        for i, doc_group in enumerate(rag_docs):
            docs = doc_group.get("docs", [])
            query = doc_group.get("query", "")
            print(f"  [{i+1}] 查询: {query}, 文档数: {len(docs)}")
    print()


def test_stream():
    """测试流式请求"""
    print("=" * 50)
    print("2. 测试流式请求 (stream=true)")
    print("=" * 50)

    payload = {
        "model": "smart-sweep-agent",
        "messages": [
            {"role": "user", "content": "深圳今天天气怎么样？"}
        ],
        "stream": True
    }

    resp = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, stream=True)

    print(f"HTTP Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
    print("\n流式输出内容:\n---")

    full_text = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line == "data: [DONE]":
            print("\n--- [DONE] ---")
            break
        if line.startswith("data: "):
            try:
                chunk = json.loads(line[6:])
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    # 检查是否有 rag_docs
                    if "rag_docs" in delta:
                        rag_data = delta["rag_docs"]
                        docs = rag_data.get("docs", [])
                        print(f"\n📚 [RAG 参考资料: {len(docs)} 篇文档]")
                    content = delta.get("content", "")
                    if content:
                        print(content, end="", flush=True)
                        full_text += content
            except json.JSONDecodeError:
                pass

    print(f"\n\n完整回复长度: {len(full_text)} 字符")
    print()


if __name__ == "__main__":
    test_non_stream()
    test_stream()
