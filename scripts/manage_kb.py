"""
知识库管理脚本

提供文档的 列表 / 删除 / 更新 等管理操作，无需重建整个知识库。

用法:
    python scripts/manage_kb.py list                      # 列出所有已入库文件
    python scripts/manage_kb.py delete <source>            # 删除指定来源的所有文档
    python scripts/manage_kb.py delete --id 123,456        # 按 ID 删除文档块
    python scripts/manage_kb.py update <file_path>         # 更新指定文件的文档
    python scripts/manage_kb.py delete --all --yes         # 清空集合（危险）
"""
import argparse
import os
import sys

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.rag_service import RAGSummarizeService
from utils.config_handler import rag_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger


def cmd_list(rag: RAGSummarizeService, _args: argparse.Namespace) -> None:
    """列出所有已入库文件及统计信息"""
    sources = rag.get_document_sources()
    total = rag.get_document_count()

    print(f"\n知识库统计:")
    print(f"  文档块总数: {total}")
    print(f"  来源文件数: {len(sources)}")
    if sources:
        print(f"\n已入库文件:")
        for src in sources:
            print(f"  📄 {src}")
    else:
        print("  (空)")
    print()


def cmd_delete(rag: RAGSummarizeService, args: argparse.Namespace) -> None:
    """删除文档"""
    # --all: 清空集合
    if args.all:
        confirm = args.yes or _confirm("⚠️  将清空整个知识库集合，所有文档块将被删除。确认？")
        if not confirm:
            print("已取消。")
            return
        rag.vector_store_service.drop_collection()
        # 也清空 MD5 缓存
        md5_path = rag.vector_store_service.md5_store_path
        if os.path.exists(md5_path):
            os.remove(md5_path)
            print(f"  ✅ MD5 缓存已清除: {md5_path}")
        print("✅ 集合已清空，需要重新初始化才能继续使用")
        return

    # --id: 按 ID 删除
    if args.id:
        try:
            ids = [int(i.strip()) for i in args.id.split(",")]
        except ValueError:
            print("❌ ID 格式错误，请使用逗号分隔的整数，如: --id 123,456")
            return

        confirm = args.yes or _confirm(f"⚠️  将删除 {len(ids)} 个指定 ID 的文档块。确认？")
        if not confirm:
            print("已取消。")
            return

        deleted = rag.delete_document_by_ids(ids)
        print(f"✅ 已删除 {deleted} 条文档块")
        return

    # 按 source 删除
    source = args.source
    if not source:
        print("❌ 请指定要删除的文件来源，或使用 --id / --all")
        return

    # 支持相对路径 → 绝对路径
    if not os.path.isabs(source):
        source = get_abs_path(source)

    confirm = args.yes or _confirm(f'⚠️  将删除来源为 "{source}" 的所有文档块。确认？')
    if not confirm:
        print("已取消。")
        return

    deleted = rag.delete_document_by_source(source)
    print(f"✅ 已删除 {deleted} 条文档块")


def cmd_update(rag: RAGSummarizeService, args: argparse.Namespace) -> None:
    """更新文档"""
    file_path = args.file_path
    if not file_path:
        print("❌ 请指定要更新的文件路径")
        return

    # 支持相对路径 → 绝对路径
    if not os.path.isabs(file_path):
        file_path = get_abs_path(file_path)

    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return

    confirm = args.yes or _confirm(
        f'⚠️  将更新文件 "{file_path}" 的知识库文档。\n'
        f"   此操作将删除旧条目并重新加载。确认？"
    )
    if not confirm:
        print("已取消。")
        return

    inserted = rag.update_document(file_path)
    if inserted > 0:
        print(f"✅ 已更新文档，共 {inserted} 个文档块")
    else:
        print(f"❌ 更新失败，请检查文件格式是否支持")


def _confirm(message: str) -> bool:
    """交互式确认

    Args:
        message: 确认提示信息

    Returns:
        用户是否确认
    """
    print()
    response = input(f"{message} [y/N]: ")
    return response.lower() in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(
        description="知识库管理工具 — 文档的列表、删除、更新操作",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/manage_kb.py list
  python scripts/manage_kb.py delete "data/故障排除.txt"
  python scripts/manage_kb.py delete --id 123,456
  python scripts/manage_kb.py update "data/故障排除.txt" --yes
  python scripts/manage_kb.py delete --all --yes
        """,
    )

    # 全局参数
    parser.add_argument("--yes", "-y", action="store_true", help="跳过确认提示，直接执行")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # list 子命令
    subparsers.add_parser("list", help="列出所有已入库文件及统计信息")

    # delete 子命令
    delete_parser = subparsers.add_parser("delete", help="删除文档")
    delete_parser.add_argument("source", nargs="?", default=None, help="文件路径（来源）")
    delete_parser.add_argument("--id", type=str, default=None, help="按逗号分隔的 ID 列表删除，如 --id 123,456")
    delete_parser.add_argument("--all", action="store_true", help="清空整个集合（危险）")
    delete_parser.add_argument("--yes", "-y", action="store_true", help="跳过确认提示，直接执行")

    # update 子命令
    update_parser = subparsers.add_parser("update", help="更新指定文件的文档")
    update_parser.add_argument("file_path", nargs="?", default=None, help="文件路径")
    update_parser.add_argument("--yes", "-y", action="store_true", help="跳过确认提示，直接执行")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 初始化 RAG 服务
    print("初始化 RAG 服务...")
    rag = RAGSummarizeService()

    # 路由到对应命令
    commands = {
        "list": cmd_list,
        "delete": cmd_delete,
        "update": cmd_update,
    }
    handler = commands.get(args.command)
    if handler:
        handler(rag, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
