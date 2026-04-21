import os
import json
import pymongo
import re

def migrate_all_files_to_mongodb():
    # 1. MongoDB 연결
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["crawling_db"]
    collection = db["camp_reviews"]

    directory_path = "./review"
    
    # 2. 파일 리스트 가져오기 및 정렬
    # 파일명 내부의 첫 번째 숫자(camp_id)를 기준으로 오름차순 정렬합니다.
    file_list = [f for f in os.listdir(directory_path) if f.endswith(".jsonl")]
    file_list.sort(key=lambda x: int(re.findall(r'\d+', x)[0]))

    for filename in file_list:
        file_path = os.path.join(directory_path, filename)
        parts = filename.replace(".jsonl", "").split("_")
        
        # 기본 정보 초기화
        camp_id = parts[1]
        naver_id = None
        total_count = 0
        reviews = []

        # 3. 파일 유형에 따른 데이터 파싱
        if "NOT_FOUND" in filename:
            # NOT_FOUND 파일: id 외 정보 없음 (빈 리스트 저장)
            print(f"Processing (Empty): {filename}")
        else:
            # 정상 데이터 파일: camp_1656_1262665220_total_3483.jsonl
            try:
                naver_id = parts[2]
                total_count = int(parts[4])

                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            raw_data = json.loads(line)
                            reviews.append({
                                "content": raw_data.get("content", ""),
                                "date": raw_data.get("date", ""),
                                "rating": raw_data.get("rating", "")
                            })
            except (IndexError, ValueError) as e:
                print(f"Error parsing filename structure: {filename}")

        # 4. MongoDB 저장 (정상 파일 & NOT_FOUND 모두 저장)
        document = {
            "camp_id": camp_id,
            "naver_id": naver_id,
            "total_count": total_count,
            "reviews": reviews,
            "status": "success" if "NOT_FOUND" not in filename else "not_found"
        }

        collection.insert_one(document)
        print(f"Successfully saved ID {camp_id}: {len(reviews)} reviews.")

if __name__ == "__main__":
    migrate_all_files_to_mongodb()