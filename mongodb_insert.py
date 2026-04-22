import os
import json
import pymongo

def migrate_jsonl_to_mongodb():
    # 1. MongoDB 연결 설정 (포트 50211 유지)
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["crawling_db"]  # 데이터베이스 이름
    collection = db["camp_reviews"]  # 컬렉션 이름

    # 기존 데이터가 섞이지 않게 싹 비우고 다시 넣고 싶다면 주석(#)을 해제하세요.
    # collection.delete_many({}) 

    directory_path = "./review"  # jsonl 파일들이 있는 디렉토리 경로

    # 2. 파일 목록 가져오기 (NOT_FOUND 제외 조건 삭제! 전부 가져옵니다)
    all_files = os.listdir(directory_path)
    target_files = [f for f in all_files if f.endswith(".jsonl")]

    # 3. 파일 이름에서 숫자(camp_id) 기준으로 정렬
    sorted_files = sorted(target_files, key=lambda x: int(x.split("_")[1]))

    # 4. 파일 순회 및 DB 저장
    for filename in sorted_files:
        parts = filename.replace(".jsonl", "").split("_")
        camp_id = parts[1]
        
        # ✅ [핵심 추가] NOT_FOUND 파일일 경우 안전하게 처리
        if "NOT_FOUND" in filename:
            naver_id = "NOT_FOUND"
            total_count = 0
        else:
            naver_id = parts[2]
            total_count = int(parts[4])

        reviews = []
        file_path = os.path.join(directory_path, filename)

        # JSONL 파일 읽기
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    raw_data = json.loads(line)
                    
                    review_obj = {
                        "content": raw_data.get("content", ""),
                        "date": raw_data.get("date", "").replace(" 월요일", "").replace(" 토요일", ""),
                    }
                    reviews.append(review_obj)

        # 최종 도큐먼트 구조 생성 (NOT_FOUND 파일은 reviews가 [] 빈 리스트로 들어감)
        document = {
            "camp_id": camp_id,
            "naver_id": naver_id,
            "total_count": total_count,
            "reviews": reviews
        }

        # MongoDB 저장
        collection.insert_one(document)
        print(f"Successfully imported: {filename} ({len(reviews)} reviews)")

if __name__ == "__main__":
    migrate_jsonl_to_mongodb()
