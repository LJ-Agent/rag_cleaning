"""Compile proto files to Python gRPC stubs.

Usage: python scripts/compile_proto.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PROTO_DIR = PROJECT_ROOT / "proto"
OUTPUT_DIR = PROJECT_ROOT / "src" / "communication" / "grpc_server" / "generated"


def compile_proto():
    """Compile cleaning.proto to Python gRPC code."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    proto_file = PROTO_DIR / "cleaning.proto"
    if not proto_file.exists():
        print(f"Proto file not found: {proto_file}")
        sys.exit(1)

    import grpc_tools.protoc

    # Compile protobuf
    result = grpc_tools.protoc.main([
        "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}",
        f"--python_out={OUTPUT_DIR}",
        f"--grpc_python_out={OUTPUT_DIR}",
        str(proto_file),
    ])

    if result != 0:
        print(f"Proto compilation failed with exit code {result}")
        sys.exit(result)

    # Fix import paths in generated grpc file
    grpc_file = OUTPUT_DIR / "cleaning_pb2_grpc.py"
    if grpc_file.exists():
        content = grpc_file.read_text(encoding="utf-8")
        content = content.replace("import cleaning_pb2", "from . import cleaning_pb2")
        grpc_file.write_text(content, encoding="utf-8")

    print(f"Proto compiled successfully: {OUTPUT_DIR}")
    print(f"  - {OUTPUT_DIR / 'cleaning_pb2.py'}")
    print(f"  - {OUTPUT_DIR / 'cleaning_pb2_grpc.py'}")


if __name__ == "__main__":
    compile_proto()
