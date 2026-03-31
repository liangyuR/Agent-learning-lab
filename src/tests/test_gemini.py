from google import genai
from dotenv import load_dotenv


def main() -> None:
    # 读取 .env 中的 GEMINI_API_KEY
    load_dotenv()

    # 官方 SDK 会自动从环境变量读取 GEMINI_API_KEY
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents="请用一句话解释什么是大语言模型。",
    )

    print(response.text)


if __name__ == "__main__":
    main()