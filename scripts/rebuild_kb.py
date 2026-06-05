"""
知识库重建脚本

删除旧的 Milvus 集合和 MD5 缓存，用最新的分块配置重新加载所有文档。
通常在修改 chunk_size / chunk_overlap / separators 后运行。

用法:
    python scripts/rebuild_kb.py          # 带确认提示
    python scripts/rebuild_kb.py --yes    # 跳过确认，直接执行
"""
import os
import sys
import argparse

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.path_tool import get_abs_path
from utils.config_handler import chroma_conf, rag_conf
from utils.logger_handler import logger


def main():
    parser = argparse.ArgumentParser(description="重建 Milvus 知识库")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认，直接执行")
    args = parser.parse_args()

    # ---- 显示当前配置 ----
    chunk_size = chroma_conf.get("chunk_size", "?")
    chunk_overlap = chroma_conf.get("chunk_overlap", "?")
    collection_name = rag_conf.get("milvus", {}).get("collection_name", "?")
    db_path = get_abs_path(rag_conf.get("milvus", {}).get("db_path", "milvus.db"))
    data_path = get_abs_path(chroma_conf.get("data_path", "data"))
    md5_path = get_abs_path(chroma_conf.get("md5_hex_store", "md5.txt"))

    print("=" * 60)
    print("  知识库重建")
    print("=" * 60)
    print(f"  集合名称    : {collection_name}")
    print(f"  数据库路径  : {db_path}")
    print(f"  数据目录    : {data_path}")
    print(f"  MD5 缓存    : {md5_path}")
    print(f"  chunk_size  : {chunk_size}")
    print(f"  chunk_overlap: {chunk_overlap}")
    print("=" * 60)

    # ---- 确认 ----
    if not args.yes:
        print()
        confirm = input("⚠️  将删除旧集合和 MD5 缓存，重新嵌入所有文档。确认？[y/N]: ")
        if confirm.lower() not in ("y", "yes"):
            print("已取消。")
            return

    # ---- Step 1: 删除旧集合 ----
    print("\n[1/3] 删除旧 Milvus 集合...")
    from rag.vector_store import VectorStoreService

    vs = VectorStoreService()
    old_count = vs._get_document_count()
    print(f"  当前文档块数量: {old_count}")

    vs.drop_collection()
    print("  ✅ 旧集合已删除")

    # ---- Step 2: 清除 MD5 缓存 ----
    print("\n[2/3] 清除 MD5 缓存...")
    if os.path.exists(md5_path):
        os.remove(md5_path)
        print(f"  ✅ {md5_path} 已删除")
    else:
        print(f"  ⏭️  {md5_path} 不存在，跳过")

    # ---- Step 3: 重新初始化并加载文档 ----
    print("\n[3/3] 重新加载文档...")
    vs2 = VectorStoreService()
    vs2.load_documents()
    new_count = vs2._get_document_count()
    print(f"  ✅ 加载完成，文档块数量: {new_count}")

    # ---- 汇总 ----
    print()
    print("=" * 60)
    print("  重建完成！")
    print(f"  旧文档块: {old_count} → 新文档块: {new_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
