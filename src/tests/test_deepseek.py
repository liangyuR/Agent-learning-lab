import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from main import build_deepseek_client, call_model


def main() -> None:
    # 读取 .env 中的 DEEPSEEK_API_KEY
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("缺少 DEEPSEEK_API_KEY")

    client = build_deepseek_client(api_key)
    try:
        response = call_model(
            client,
            "你是一个简洁的中文助手。",
            "请用一句话解释什么是大语言模型。",
            max_output_tokens=200,
        )
        print(response.text)
    finally:
        client.close()


if __name__ == "__main__":
    main()
