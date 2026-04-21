import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
import joblib
import re

# 폰트 및 경로 설정
os.makedirs('static/images', exist_ok=True)
plt.rc('font', family='Malgun Gothic')

# DB 및 모델 로드
MARIA_URL = "mysql+pymysql://root:pass123#@127.0.0.1:3306/camping_db?charset=utf8mb4"
MONGO_URL = "mongodb://localhost:27017"
model = joblib.load('camp_sentiment_model.pkl')
tfidf = joblib.load('camp_tfidf_vectorizer.pkl')

async def generate_region_sentiment_map():
    # 1. MariaDB에서 캠핑장 ID와 주소 가져오기
    engine = create_engine(MARIA_URL)
    with engine.connect() as conn:
        df_camps = pd.read_sql(text("SELECT camspot_id, address FROM campsites"), conn)
    
    df_camps['region'] = df_camps['address'].apply(lambda x: x.split()[0] if x else '미분류')

    # 2. MongoDB에서 모든 리뷰 가져와 감성 분석 수행
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    collection = mongo_client.crawling_db.camp_reviews
    
    sentiment_data = []
    
    async for doc in collection.find({}, {"camp_id": 1, "reviews.content": 1}):
        camp_id = int(doc['camp_id'])
        region = df_camps.loc[df_camps['camspot_id'] == camp_id, 'region'].values
        if len(region) == 0: continue
        region = region[0]

        for rev in doc.get('reviews', []):
            content = rev.get('content', '')
            if not content: continue
            
            # 감성 예측 (1: 긍정, 0: 부정)
            pred = model.predict(tfidf.transform([content]))[0]
            sentiment_data.append({'region': region, 'sentiment': pred})

    df_sentiment = pd.DataFrame(sentiment_data)
    
    # 3. 지역별 긍정/부정 비율 계산
    stats = df_sentiment.groupby('region')['sentiment'].value_counts(normalize=True).unstack().fillna(0)
    stats.columns = ['부정비율', '긍정비율']
    stats = stats.sort_values(by='긍정비율', ascending=False)

    # 4. 시각화 (수평 바 차트로 지역별 비교)
    # 지도로 표시하기 위해서는 GeoJSON 데이터가 필요하므로, 
    # 우선 가장 직관적인 지역별 비교 차트를 생성합니다.
    plt.figure(figsize=(12, 10))
    stats[['긍정비율', '부정비율']].plot(kind='barh', stacked=True, 
                                     color=['#ff9999', '#66b3ff'], ax=plt.gca())
    
    plt.title("전국 지역별 캠핑 감성 지수 (긍정 vs 부정)", fontsize=16, fontweight='bold', pad=20)
    plt.xlabel("비율")
    plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=2)
    plt.tight_layout()

    save_path = 'static/images/region_sentiment.png'
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"✅ 지역별 감성 분석 이미지 저장 완료: {save_path}")

if __name__ == "__main__":
    asyncio.run(generate_region_sentiment_map())