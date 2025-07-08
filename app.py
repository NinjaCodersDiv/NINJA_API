from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import os
from datetime import datetime
import shutil
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
import psycopg2
from psycopg2.extras import RealDictCursor

# تنظیمات اولیه
app = FastAPI(
    title="سیستم مدیریت مقالات",
    description="یک API کامل برای مدیریت مقالات با قابلیت CRUD و اتصال به PostgreSQL",
    version="2.0.0"
)

# تنظیمات CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# مدل داده مقاله با استفاده از Pydantic v2
class ArticleBase(BaseModel):
    title: str
    category: str
    excerpt: str
    image: str
    date: str
    author: str
    authorImage: str
    content: str

class ArticleCreate(ArticleBase):
    pass

class Article(ArticleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# مدل پایه SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass

# مدل دیتابیس
class DBArticle(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), index=True)
    category = Column(String(100))
    excerpt = Column(String(300))
    image = Column(String(200))
    date = Column(String(50))
    author = Column(String(100))
    authorImage = Column(String(200))
    content = Column(Text)

# اتصال به پایگاه داده PostgreSQL
SQLALCHEMY_DATABASE_URL = "postgresql://data_ovro_user:HwvRmCN0ZvW38pz9xs9FtzUjROp7nXOY@dpg-d1madhadbo4c73f2vfdg-a/data_ovro"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ایجاد جداول (اگر وجود نداشته باشند)
Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# مسیرهای ذخیره‌سازی تصاویر
ARTICLE_IMAGES_DIR = "articles/images"
AUTHOR_IMAGES_DIR = "articles/author_images"

# ایجاد پوشه‌ها اگر وجود نداشته باشند
os.makedirs(ARTICLE_IMAGES_DIR, exist_ok=True)
os.makedirs(AUTHOR_IMAGES_DIR, exist_ok=True)

# تابع کمکی برای تاریخ
def get_persian_date():
    return datetime.now().strftime("%Y-%m-%d")

# روت‌های API
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "به سیستم مدیریت مقالات خوش آمدید"}

@app.get("/articles/", response_model=List[Article], tags=["مقالات"])
async def get_all_articles_endpoint(db: Session = Depends(get_db)):
    """دریافت لیست تمام مقالات"""
    articles = db.query(DBArticle).all()
    return articles

@app.get("/articles/{article_id}", response_model=Article, tags=["مقالات"])
async def get_article_endpoint(article_id: int, db: Session = Depends(get_db)):
    """دریافت یک مقاله خاص"""
    article = db.query(DBArticle).filter(DBArticle.id == article_id).first()
    if article is None:
        raise HTTPException(status_code=404, detail="مقاله یافت نشد")
    return article

@app.post("/articles/", response_model=Article, tags=["مقالات"])
async def create_article_endpoint(
    title: str = Form(...),
    category: str = Form(...),
    excerpt: str = Form(...),
    image: UploadFile = File(...),
    author: str = Form(...),
    authorImage: UploadFile = File(...),
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """ایجاد مقاله جدید"""
    try:
        # ذخیره تصاویر با نام‌های منحصر به فرد
        timestamp = int(datetime.now().timestamp())
        image_filename = f"{timestamp}_{image.filename}"
        image_path = os.path.join(ARTICLE_IMAGES_DIR, image_filename)
        
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        author_image_filename = f"{timestamp}_{authorImage.filename}"
        author_image_path = os.path.join(AUTHOR_IMAGES_DIR, author_image_filename)
        
        with open(author_image_path, "wb") as buffer:
            shutil.copyfileobj(authorImage.file, buffer)
        
        # ایجاد مقاله در دیتابیس
        db_article = DBArticle(
            title=title,
            category=category,
            excerpt=excerpt,
            image=f"images/{image_filename}",
            date=get_persian_date(),
            author=author,
            authorImage=f"images/{author_image_filename}",
            content=content
        )
        
        db.add(db_article)
        db.commit()
        db.refresh(db_article)
        
        return db_article
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"خطا در ایجاد مقاله: {str(e)}"
        )

@app.put("/articles/{article_id}", response_model=Article, tags=["مقالات"])
async def update_article_endpoint(
    article_id: int,
    title: str = Form(...),
    category: str = Form(...),
    excerpt: str = Form(...),
    image: Optional[UploadFile] = File(None),
    author: str = Form(...),
    authorImage: Optional[UploadFile] = File(None),
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """به‌روزرسانی مقاله موجود"""
    db_article = db.query(DBArticle).filter(DBArticle.id == article_id).first()
    if db_article is None:
        raise HTTPException(status_code=404, detail="مقاله یافت نشد")
    
    try:
        # مدیریت تصاویر
        if image:
            timestamp = int(datetime.now().timestamp())
            image_filename = f"{timestamp}_{image.filename}"
            new_image_path = os.path.join(ARTICLE_IMAGES_DIR, image_filename)
            
            with open(new_image_path, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            
            # حذف تصویر قدیمی اگر وجود داشته باشد
            old_image_path = os.path.join(ARTICLE_IMAGES_DIR, os.path.basename(db_article.image))
            if os.path.exists(old_image_path):
                os.remove(old_image_path)
            
            db_article.image = f"images/{image_filename}"
        
        if authorImage:
            timestamp = int(datetime.now().timestamp())
            author_image_filename = f"{timestamp}_{authorImage.filename}"
            new_author_image_path = os.path.join(AUTHOR_IMAGES_DIR, author_image_filename)
            
            with open(new_author_image_path, "wb") as buffer:
                shutil.copyfileobj(authorImage.file, buffer)
            
            # حذف تصویر قدیمی نویسنده اگر وجود داشته باشد
            old_author_image_path = os.path.join(AUTHOR_IMAGES_DIR, os.path.basename(db_article.authorImage))
            if os.path.exists(old_author_image_path):
                os.remove(old_author_image_path)
            
            db_article.authorImage = f"images/{author_image_filename}"
        
        # به‌روزرسانی فیلدها
        db_article.title = title
        db_article.category = category
        db_article.excerpt = excerpt
        db_article.author = author
        db_article.content = content
        
        db.commit()
        db.refresh(db_article)
        
        return db_article
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"خطا در به‌روزرسانی مقاله: {str(e)}"
        )

@app.delete("/articles/{article_id}", tags=["مقالات"])
async def delete_article_endpoint(article_id: int, db: Session = Depends(get_db)):
    """حذف مقاله"""
    db_article = db.query(DBArticle).filter(DBArticle.id == article_id).first()
    if db_article is None:
        raise HTTPException(status_code=404, detail="مقاله یافت نشد")
    
    try:
        # حذف فایل‌های تصویر مرتبط
        image_path = os.path.join(ARTICLE_IMAGES_DIR, os.path.basename(db_article.image))
        author_image_path = os.path.join(AUTHOR_IMAGES_DIR, os.path.basename(db_article.authorImage))
        
        if os.path.exists(image_path):
            os.remove(image_path)
        if os.path.exists(author_image_path):
            os.remove(author_image_path)
        
        db.delete(db_article)
        db.commit()
        return {"message": "مقاله با موفقیت حذف شد"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"خطا در حذف مقاله: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
