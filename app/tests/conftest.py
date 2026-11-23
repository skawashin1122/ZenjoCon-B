import os

# テストは毎回まっさらなメモリ上のDBと、仮AIで動かす（本物のAPIキーは使わない）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = ""
os.environ["MIN_WAGE"] = "1023"
