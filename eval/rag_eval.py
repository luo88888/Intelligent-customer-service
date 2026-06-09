import json
import os
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from datasets import Dataset
from typing import Optional
from ragas.cost import TokenUsage
from ragas import evaluate
from ragas.run_config import RunConfig
from ragas.metrics._answer_relevance import AnswerRelevancy
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._context_precision import ContextPrecision
from ragas.metrics._context_recall import ContextRecall
from langchain_core.outputs import LLMResult
from langchain_core.callbacks import BaseCallbackHandler
from tqdm import tqdm

class PrintLLMOutputCallback(BaseCallbackHandler):
    def on_llm_end(self, response: LLMResult, **kwargs: any) -> None:
        return
        print("\n====== LLM 模型输出 ======")
        for gen in response.generations:
            for g in gen:
                print(g.text)
        print("==========================\n")


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from model.factory import create_chat_model, create_embedding_model
from utils.path_tool import get_abs_path
from rag.rag_service import RAGSummarizeService


total_input_tokens = 0
total_output_tokens = 0


def token_usage_parser(result: LLMResult) -> TokenUsage:
    # print("llm_output:", result.model_dump())  # 先看结构
    try:
        token_data = result.model_dump()["generations"][0][0]["generation_info"]["token_usage"]
        # print("token_data:", token_data)
    except KeyError:
        token_data = {}
    # 更新全局 token 统计
    global total_input_tokens, total_output_tokens
    total_input_tokens += token_data.get("input_tokens", 0)
    total_output_tokens += token_data.get("output_tokens", 0)
    return TokenUsage(
        input_tokens=token_data.get("input_tokens", 0),
        output_tokens=token_data.get("output_tokens", 0),
    )


def eval_rag(
    data_path: str,
    output_path: str,
    rag: RAGSummarizeService,
    batch_size: Optional[int]=None,
    n: int=0,
    max_workers: int=16,
    eval_max_workers: int=16,
):
    """评估 RAG 系统的性能

    Args:
        data_path: 评估数据 JSON 文件路径
        output_path: 结果输出 CSV 文件路径
        rag: RAGSummarizeService 实例
        batch_size: ragas evaluate 的批处理大小
        n: 限制评估数据条数（0 = 全部）
        max_workers: RAG 检索阶段的并发数（默认 16）
        eval_max_workers: ragas 评估阶段的并发数（默认 16，LLM 调用密集，不宜过高）
    """
    data_dict = json.load(open(data_path, "r", encoding="utf-8"))

    if any(key not in data_dict for key in ["question", "ground_truth", "contexts", "answer"]):
        raise ValueError("数据中缺少必要的字段：question, ground_truth, contexts, answer")
    if len(data_dict["question"]) != len(data_dict["ground_truth"]):
        raise ValueError("question 和 ground_truth 字段的长度不一致")
    data_dict["contexts"] = []
    data_dict["answer"] = []

    llm = create_chat_model()
    embeddings = create_embedding_model()

    if n > 0:
        data_dict["question"] = data_dict["question"][:n]
        data_dict["ground_truth"] = data_dict["ground_truth"][:n]

    print(f"共 {len(data_dict['question'])} 条数据，RAG 检索并发数: {max_workers}...")

    # 阶段 1: 并行 RAG 检索（I/O 密集型，使用多线程）
    questions = data_dict["question"]
    results: list = [None] * len(questions)

    def fetch_rag(idx: int, query: str):
        """单条 RAG 检索任务，返回独立文档列表供 ragas 逐文档评估"""
        answer, doc_texts = rag.rag_summarize_with_docs(query)
        return idx, answer, doc_texts

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_rag, i, q): i
            for i, q in enumerate(questions)
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="获取 RAG 结果"):
            idx, answer, doc_texts = future.result()
            results[idx] = (answer, doc_texts)

    for answer, doc_texts in results:
        data_dict["answer"].append(answer)
        data_dict["contexts"].append(doc_texts)

    dataset = Dataset.from_dict(data_dict)

    print(f"dataset: {dataset}")
    print(f'前 {min(5, len(dataset))} 条数据:')
    for i in range(min(5, len(dataset))):
        print(f'-------------------第 {i} 条数据-------------------')
        for key, value in dataset[i].items():
            print(f'{key}: {value}')

    global total_input_tokens, total_output_tokens
    total_input_tokens = 0
    total_output_tokens = 0

    print('数据生成完毕，开始评估...')
    metrics = [
        AnswerRelevancy(strictness=1),
        Faithfulness(),
        ContextPrecision(),   # 上下文精度最耗时，检索文档串行调用 LLM N 次
        ContextRecall(),
    ]
    results = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        callbacks=[PrintLLMOutputCallback()],
        embeddings=embeddings,
        experiment_name="rag_eval",
        token_usage_parser=token_usage_parser,  # type: ignore
        raise_exceptions=False,  # LLM 调用可能出现异常，不因个别识别中断评估流程
        batch_size=batch_size,
        run_config=RunConfig(max_workers=eval_max_workers, timeout=600),
    )
    print(f"results: {results}")
    print(f"total_input_tokens: {total_input_tokens}")
    print(f"total_output_tokens: {total_output_tokens}")

    df = results.to_pandas()
    df.to_csv(output_path, index=False)
    print(f"结果已保存到 {output_path}")

    return results


def overall_eval():
    input_tokens, output_tokens = 0, 0
    start_time = datetime.datetime.now()
    rag = RAGSummarizeService()
    data_path_list = [get_abs_path(f"eval/data/data_{level}.json") for level in ["easy","middle", "hard"]]
    output_path_list = [get_abs_path(f"eval/result/rag_eval_{level}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv") for level in ["easy","middle", "hard"]]
    print("数据路径列表:")
    for data_path in data_path_list:
        print(data_path)
    print("输出路径列表:")
    for output_path in output_path_list:
        print(output_path)
    results_list = []

    for data_path, output_path in zip(data_path_list, output_path_list):
        results = eval_rag(
            data_path=data_path,
            output_path=output_path,
            rag=rag,
            batch_size=8,
            max_workers=8,  # Milvus 侧已用 BoundedSemaphore(16) 限流，这里可以设高
            eval_max_workers=8,  # ragas 评估阶段每个样本多次串行 LLM 调用，并发过高易超时
        )
        results_list.append(results)
        input_tokens += total_input_tokens
        output_tokens += total_output_tokens

    # 汇总结果
    print("="*30 + "汇总结果" + "="*30)
    for level, results in zip(["easy","middle", "hard"], results_list):
        print(f"level: {level}")
        print(f"results: {results}")
        print("="*60)

    print(f"total_input_tokens: {input_tokens}")
    print(f"total_output_tokens: {output_tokens}")
    end_time = datetime.datetime.now()
    print(f"耗时: {end_time - start_time}秒")


# python -m eval.rag_eval
if __name__ == "__main__":
    # rag = RAGSummarizeService()
    # data_path = get_abs_path("eval/data.json")
    # output_path = get_abs_path(f"eval/result/rag_eval_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    # eval_rag(
    #     data_path=data_path,
    #     output_path=output_path,
    #     rag=rag,
    #     batch_size=8,
    #     n=3
    # )

    overall_eval()