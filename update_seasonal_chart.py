import os
import re
import numpy as np
import matplotlib.pyplot as plt
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import joblib

# [설정] 환경 및 폰트 설정
plt.rc('font', family='Malgun Gothic')
plt.rc('axes', unicode_minus=False)

# [설정] DB 및 경로 정보
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "crawling_db"
COLLECTION_NAME = "camp_reviews"
CHARTS_DIR = "static/charts"

# [로드] 감성 분석 모델 및 벡터라이저 (파일명 확인 필요)
model = joblib.load('camp_sentiment_model.pkl')
tfidf = joblib.load('camp_tfidf_vectorizer.pkl')

def get_season(date_str):
    """'2026년 3월 13일' 형식에서 월을 추출하여 계절 반환"""
    try:
        match = re.findall(r'\d+', date_str)
        if len(match) >= 2:
            month = int(match[1])
            if month in [3, 4, 5]: return '봄'
            elif month in [6, 7, 8]: return '여름'
            elif month in [9, 10, 11]: return '가을'
            else: return '겨울'
    except Exception:
        return None
    return None

def save_individual_chart(labels, values, title, filename, color):
    """단일 막대 차트를 생성하고 저장하는 함수"""
    plt.clf()
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(labels))

    bars = ax.bar(x, values, color=color, width=0.6)
    
    # 막대 위에 숫자 표시
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{int(height)}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), 
                    textcoords="offset points",
                    ha='center', va='bottom')

    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel('리뷰 수')
    
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    plt.tight_layout()
    
    file_path = os.path.join(CHARTS_DIR, filename)
    plt.savefig(file_path, dpi=120)
    plt.close()
    print(f"저장 완료: {file_path}")

async def generate_seasonal_charts_sep():
    client = AsyncIOMotorClient(MONGO_URL)
    review_collection = client[DB_NAME][COLLECTION_NAME]
    
    os.makedirs(CHARTS_DIR, exist_ok=True)

    stats = {
        '봄': {'pos': 0, 'neg': 0},
        '여름': {'pos': 0, 'neg': 0},
        '가을': {'pos': 0, 'neg': 0},
        '겨울': {'pos': 0, 'neg': 0}
    }

    try:
        print("데이터 분석 중...")
        cursor = review_collection.find({})
        async for doc in cursor:
            for rev in doc.get('reviews', []):
                content = rev.get('content', '')
                date_str = rev.get('date', '')
                season = get_season(date_str)
                
                if content and season:
                    pred = model.predict(tfidf.transform([content]))[0]
                    if pred == 1:
                        stats[season]['pos'] += 1
                    else:
                        stats[season]['neg'] += 1

        seasons = ['봄', '여름', '가을', '겨울']
        pos_counts = [stats[s]['pos'] for s in seasons]
        neg_counts = [stats[s]['neg'] for s in seasons]

        # 1. 긍정 차트 저장
        save_individual_chart(seasons, pos_counts, '계절별 긍정 리뷰 분포', 'seasonal_pos.png', '#10B981')
        
        # 2. 부정 차트 저장
        save_individual_chart(seasons, neg_counts, '계절별 부정 리뷰 분포', 'seasonal_neg.png', '#EF4444')

    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(generate_seasonal_charts_sep())