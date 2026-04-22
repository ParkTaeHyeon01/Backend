import os
import asyncio
import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
from PIL import Image
from collections import Counter
from konlpy.tag import Okt
from wordcloud import WordCloud
from motor.motor_asyncio import AsyncIOMotorClient

# --- [1. 환경 및 경로 설정] ---
os.environ['JAVA_HOME'] = r'C:\Program Files\Java\jdk-17.0.18' # 환경에 맞게 수정 필요
FONT_PATH = 'C:/Windows/Fonts/malgun.ttf' 
STOPWORDS = [
    '있다', '없다', '좋다', '같다', '이다', '아니다', '그냥', '진짜', '너무', 
    '정말', '매우', '아주', '조금', '많다', '적다', '하나', '번', '들다', 
    '하다', '되다', '보고', '가다', '오다', '여기', '저기', '생각', '느낌',
    '때문', '정도', '다시', '항상', '보통', '전체', '부분', '이것', '그것',
    '다음', '보기', '자주', '사용', '통해', '가지', '경우', '내용', '확인',
    '그렇다', '이용', '우리', '캠핑', '캠핑장', '예약', '방문', '사이트'
] #

# --- [2. 분석 엔진 로드] ---
print("-> 모델 및 형태소 분석기 로드 중...")
model = joblib.load('camp_sentiment_model.pkl') #
tfidf = joblib.load('camp_tfidf_vectorizer.pkl') #
okt = Okt() 
tfidf.tokenizer = okt.morphs #

async def generate_total_wordcloud():
    # MongoDB 연결
    client = AsyncIOMotorClient("mongodb://localhost:27017") #
    db = client.crawling_db
    collection = db.camp_reviews

    print("-> 전체 데이터 불러오는 중 (시간이 소요될 수 있습니다)...")
    pos_words = []
    neg_words = []
    
    cursor = collection.find({}, {"reviews.content": 1})
    
    async for doc in cursor:
        if not doc.get('reviews'): continue
        
        for rev in doc['reviews']:
            content = rev.get('content', '')
            if not content or len(content) < 5: continue
            
            # 감성 예측 (1: 긍정, 0: 부정)
            pred = model.predict(tfidf.transform([content]))[0]
            
            # 형태소 분석 및 필터링
            tokens = okt.pos(content, stem=True)
            words = [w for w, t in tokens if t in ['Noun', 'Adjective'] 
                     and len(w) > 1 and w not in STOPWORDS] #
            
            if pred == 1:
                pos_words.extend(words)
            else:
                neg_words.extend(words)

    # 결과 저장 폴더 생성
    os.makedirs('static/charts', exist_ok=True)

    # 워드클라우드 생성 함수
    def save_cloud(word_list, filename, sentiment_type):
        counts = Counter(word_list)
        # 빈도수가 너무 낮은 단어 제거 (전체 데이터이므로 기준을 5회로 상향)
        filtered_counts = {word: count for word, count in counts.items() if count >= 5}
        
        if not filtered_counts:
            print(f"[{sentiment_type}] 분석할 키워드가 부족합니다.")
            return

        colormap = 'summer' if sentiment_type == 'pos' else 'autumn' #

        wc = WordCloud(
            font_path=FONT_PATH,
            background_color='white',
            width=1200,
            height=800,
            colormap=colormap,
            max_words=100,           # 전체 데이터이므로 단어 수를 100개로 확장
            min_font_size=10,
            max_font_size=200,
            prefer_horizontal=0.9
        ).generate_from_frequencies(filtered_counts) #

        plt.figure(figsize=(15, 10))
        plt.imshow(wc, interpolation='bilinear')
        plt.axis('off')
        plt.title(f"전체 리뷰 { '긍정' if sentiment_type == 'pos' else '부정' } 키워드 분석", fontsize=20)
        
        save_path = f"static/charts/total_{filename}.png"
        plt.savefig(save_path, bbox_inches='tight')
        plt.close()
        print(f"-> {save_path} 저장 완료")

    # 긍정/부정 각각 생성
    save_cloud(pos_words, 'pos', 'pos')
    save_cloud(neg_words, 'neg', 'neg')
    client.close()

if __name__ == "__main__":
    asyncio.run(generate_total_wordcloud())