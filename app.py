import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from datetime import datetime

# --- CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

# Database path: Adjust this if your folder structure differs
db_path = os.path.join(basedir, "kshetrapal.db")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELS ---

class Area(db.Model):
    __tablename__ = 'area'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    map_image = db.Column(db.String(255), default="default_area.png")
    news_content = db.Column(db.Text)
    sectors = db.relationship('Sector', backref='area_ref', lazy=True, cascade="all, delete-orphan")

class Sector(db.Model):
    __tablename__ = 'sector'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    map_image = db.Column(db.String(255), default="default_sector.png")
    area_id = db.Column(db.Integer, db.ForeignKey('area.id'), nullable=False)
    societies = db.relationship('Society', backref='sector_ref', lazy=True, cascade="all, delete-orphan")

class Society(db.Model):
    __tablename__ = 'society'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50)) 
    map_image = db.Column(db.String(255), default="default_society.png")
    sector_id = db.Column(db.Integer, db.ForeignKey('sector.id'), nullable=False)

class News(db.Model):
    __tablename__ = 'news'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    sector_id = db.Column(db.Integer, db.ForeignKey('sector.id'), nullable=False)

class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    level_type = db.Column(db.String(20)) # 'area', 'sector', or 'society'
    target_id = db.Column(db.Integer, nullable=False)

# --- ROUTES ---

@app.route('/')
def home():
    areas = Area.query.all()
    hot_sectors = Sector.query.limit(4).all()
    news_feed = News.query.order_by(News.date_posted.desc()).limit(3).all()
    return render_template('home.html', areas=areas, hot_sectors=hot_sectors, news_feed=news_feed)

# --- Suggestions ---
@app.route('/api/suggestions')
def suggestions():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    
    words = q.split()
    search_term = f"%{q}%"
    results = []

    # 1. COMPOSITE SEARCH (The "Smart" part)
    if len(words) > 1:
        # Case: Area + Sector (e.g., "Rohini Sector 34")
        composite_sectors = Sector.query.join(Area).filter(
            Area.name.ilike(f"%{words[0]}%"),
            Sector.name.ilike(f"%{' '.join(words[1:])}%")
        ).limit(3).all()
        
        for s in composite_sectors:
            results.append({
                "name": f"{s.name} ({s.area_ref.name})",
                "type": "Sector",
                "search_val": s.name
            })

        # Case: Sector + Society (e.g., "Sector 70 Tulip")
        composite_societies = Society.query.join(Sector).filter(
            Sector.name.ilike(f"%{words[0]}%"),
            Society.name.ilike(f"%{' '.join(words[1:])}%")
        ).limit(3).all()

        for soc in composite_societies:
            results.append({
                "name": f"{soc.name} ({soc.sector_ref.name})",
                "type": "Society",
                "search_val": soc.name
            })

    # 2. INDIVIDUAL SEARCH (Fallback for single words)
    # Search Societies
    societies = Society.query.filter(Society.name.ilike(search_term)).limit(3).all()
    for soc in societies:
        # Avoid duplicates from composite search
        if not any(r['search_val'] == soc.name for r in results):
            results.append({
                "name": f"{soc.name} ({soc.sector_ref.name})", 
                "type": "Society", 
                "search_val": soc.name
            })
    
    # Search Sectors
    sectors = Sector.query.filter(Sector.name.ilike(search_term)).limit(3).all()
    for s in sectors:
        if not any(r['search_val'] == s.name for r in results):
            results.append({
                "name": f"{s.name} ({s.area_ref.name})", 
                "type": "Sector", 
                "search_val": s.name
            })

    return jsonify(results[:8]) # Limit total suggestions to 8

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query: return redirect(url_for('home'))

    # Hierarchy Check: Same logic as suggestions for consistency
    # 1. Exact/Partial Society
    soc = Society.query.filter(Society.name.ilike(f"%{query}%")).first()
    if soc: return render_template('Society.html', level="society", item=soc, item_name=soc.name)

    # 2. Multi-word Sector/Area check
    words = query.split()
    if len(words) > 1:
        sec = Sector.query.join(Area).filter(
            Area.name.ilike(f"%{words[0]}%"),
            Sector.name.ilike(f"%{' '.join(words[1:])}%")
        ).first()
        if sec: return render_template('Society.html', level="sector", item=sec, item_name=sec.name, societies=sec.societies)

    # 3. Standard Sector
    sec = Sector.query.filter(Sector.name.ilike(f"%{query}%")).first()
    if sec: return render_template('Society.html', level="sector", item=sec, item_name=sec.name, societies=sec.societies)

    # 4. Standard Area
    area = Area.query.filter(Area.name.ilike(f"%{query}%")).first()
    if area: return render_template('Society.html', level="area", item=area, item_name=area.name, sectors=area.sectors)

    return render_template('Society.html', item_name=query, societies=[])
# --- FORUM LOGIC ---

@app.route('/get_forum_posts')
def get_forum_posts():
    t_id = request.args.get('target_id')
    l_type = request.args.get('level_type')
    
    posts = ChatMessage.query.filter_by(level_type=l_type, target_id=t_id).order_by(ChatMessage.timestamp.asc()).all()
    
    return jsonify([{
        "user": p.user_name,
        "content": p.content,
        "date": p.timestamp.strftime('%d %b %Y'),
        "time": p.timestamp.strftime('%I:%M %p')
    } for p in posts])

@app.route('/post_to_forum', methods=['POST'])
def post_to_forum():
    data = request.get_json()
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    content = data.get('content', '').strip()
    l_type = data.get('level_type')
    t_id = data.get('target_id')

    if not all([name, phone, content, t_id]):
        return jsonify({"status": "error", "message": "Fields missing"}), 400

    # User consistency: Update all previous messages with this phone number to use the new name
    ChatMessage.query.filter_by(phone_number=phone).update({"user_name": name})

    new_msg = ChatMessage(
        content=content,
        user_name=name,
        phone_number=phone,
        level_type=l_type,
        target_id=t_id
    )
    
    db.session.add(new_msg)
    db.session.commit()
    return jsonify({"status": "success"})

# --- DATABASE SETUP ---

def setup_database():
    with app.app_context():
        db.create_all()
        # Seed logic (optional)
        if not Area.query.first():
            print("Seeding initial data...")
            gurgaon = Area(name="Gurgaon", news_content="Real estate growth in Gurgaon.")
            db.session.add(gurgaon)
            db.session.flush() # Gets ID before commit
            
            sec70 = Sector(name="Sector 70", area_id=gurgaon.id)
            db.session.add(sec70)
            db.session.flush()
            
            s1 = Society(name="Tulip Orange", type="High-rise", sector_id=sec70.id)
            db.session.add(s1)
            db.session.commit()

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)