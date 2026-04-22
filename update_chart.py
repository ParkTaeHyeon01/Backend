import os
import io
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import joblib

# [설정] 환경 및 폰트 설정
plt.rc('font', family='Malgun Gothic')
plt.rc('axes', unicode_minus=False)

# [설정] DB 및 경로 정보
MARIA_DB_URL = "mysql+pymysql://root:pass123#@localhost:3306/camping_db"
MONGO_URL = "mongodb://localhost:27017"
CHARTS_DIR = "static/charts"

# [로드] 감성 분석 모델 및 벡터라이저
model = joblib.load('camp_sentiment_model.pkl')
tfidf = joblib.load('camp_tfidf_vectorizer.pkl')

def save_region_chart(labels, values, title, filename, color):
    """단일 막대 차트를 생성하고 저장하는 함수"""
    plt.clf()
    fig, ax = plt.subplots(figsize=(12, 7))
    x = np.arange(len(labels))

    bars = ax.bar(x, values, color=color, width=0.6)
    
    # 막대 위에 수치 표시
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), 
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10)

    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel('리뷰 건수')
    
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    plt.tight_layout()
    
    file_path = os.path.join(CHARTS_DIR, filename)
    plt.savefig(file_path, dpi=120)
    plt.close()
    print(f"저장 완료: {file_path}")

async def generate_region_charts_sep():
    engine = create_engine(MARIA_DB_URL)
    client = AsyncIOMotorClient(MONGO_URL)
    review_collection = client['crawling_db']['camp_reviews']

    if not os.path.exists(CHARTS_DIR):
        os.makedirs(CHARTS_DIR)

    try:
        # 1. MariaDB에서 지역별 ID 가져오기
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    CASE 
                        WHEN address LIKE '경기%' THEN '경기'
                        WHEN address LIKE '서울%' THEN '서울'
                        WHEN address LIKE '강원%' THEN '강원'
                        WHEN address LIKE '충%' THEN '충청'
                        WHEN address LIKE '경%' THEN '경상'
                        WHEN address LIKE '전%' THEN '전라'
                        WHEN address LIKE '제주%' THEN '제주'
                        ELSE '기타'
                    END as region,
                    GROUP_CONCAT(camspot_id) as ids
                FROM campsites
                GROUP BY region
                HAVING region != '기타'
            """)
            rows = conn.execute(query).mappings().all()

        regions, pos_counts, neg_counts = [], [], []

        for row in rows:
            region_name = row['region']
            ids = row['ids'].split(',')
            p_count, n_count = 0, 0
            
            # MongoDB 리뷰 분석
            cursor = review_collection.find({"camp_id": {"$in": ids}})
            async for doc in cursor:
                for rev in doc.get("reviews", []):
                    content = rev.get("content", "")
                    if content:
                        pred = model.predict(tfidf.transform([content]))[0]
                        if pred == 1: p_count += 1
                        else: n_count += 1
            
            regions.append(region_name)
            pos_counts.append(p_count)
            neg_counts.append(n_count)

        # 2. 긍정/부정 차트 개별 저장
        save_region_chart(regions, pos_counts, '지역별 긍정 리뷰 분포', 'region_pos.png', '#10B981')
        save_region_chart(regions, neg_counts, '지역별 부정 리뷰 분포', 'region_neg.png', '#EF4444')

    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(generate_region_charts_sep())