# RAG性能指标

## 1 easy

| RAG 配置 | answer_relevancy | context_precision | faithfulness | context_recall |
| :-: | :-: | :-: | :-: | :-: |
| 递归字符分割 + qwen3.5-plus + text-embedding-v4(qwen) + final_k=3| 0.7123 | 0.9333 | 0.7983 | 0.8556 |
| 递归字符分割 + qwen3.5-plus + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序）+ dense_k=5 + sparse_k=5 + final_k=3|0.8285|0.9667|0.8169|0.9556|
| 递归字符分割 + deepseek-v4-flash + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=5 + sparse_k=5 + final_k=3|0.7379|0.9206|0.9278|0.9333|
| 递归字符分割 + deepseek-v4-flash + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=20 + sparse_k=20 + final_k=8 + 查询重写=3|0.8118|0.8823|0.9222|1.0000|

## 2 middle

| RAG 配置 | answer_relevancy | context_precision | faithfulness | context_recall |
| :-: | :-: | :-: | :-: | :-: |
| 递归字符分割 + qwen3.5-plus + text-embedding-v4(qwen) + final_k=3| 0.7537 | 0.6667 | 0.7626 | 0.6222 |
| 递归字符分割 + qwen3.5-plus + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=5 + sparse_k=5 + final_k=3|0.7675|0.8667|0.8614|0.8056|
| 递归字符分割 + deepseek-v4-flash + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=5 + sparse_k=5 + final_k=3|0.6413|0.8467|0.9667|0.7833|
| 递归字符分割 + deepseek-v4-flash + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=20 + sparse_k=20 + final_k=8 + 查询重写=3|0.8180|0.8124|0.9127|0.9000|

## 3 hard

| RAG 配置 | answer_relevancy | context_precision | faithfulness | context_recall |
| :-: | :-: | :-: | :-: | :-: |
| 递归字符分割 + qwen3.5-plus + text-embedding-v4(qwen) + final_k=3| 0.5799 | 0.5333 | 0.6424 | 0.3222 |
| 递归字符分割 + qwen3.5-plus + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=5 + sparse_k=5 + final_k=3|0.6650|0.6667|0.6035|0.3239|
| 递归字符分割 + deepseek-v4-flash + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=5 + sparse_k=5 + final_k=3|0.4741|0.7735|0.7694|0.2389|
| 递归字符分割 + deepseek-v4-flash + text-embedding-v4(qwen) + BM25 + 倒数排名融合 + gte-rerank-v2（重排序） + dense_k=20 + sparse_k=20 + final_k=8 + 查询重写=3|0.6021|0.8127|0.8157|0.4839|