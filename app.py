from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'connectly-demo-secret-2024')

# Jinja2 filter for JSON parsing in templates
app.jinja_env.filters['from_json'] = json.loads

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Use DATABASE_URL env var if set (Railway/Postgres), otherwise local SQLite.
# Railway sets DATABASE_URL with postgres:// prefix — SQLAlchemy needs postgresql://
_db_url = os.environ.get('DATABASE_URL',
                         'sqlite:///' + os.path.join(BASE_DIR, 'data', 'connectly.db'))
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# Database models
# ---------------------------------------------------------------------------

class User(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    username    = db.Column(db.String(80), unique=True, nullable=False)
    email       = db.Column(db.String(120), unique=True, nullable=False)
    full_name   = db.Column(db.String(120))
    age         = db.Column(db.Integer)
    bio         = db.Column(db.String(300))
    avatar_emoji= db.Column(db.String(10), default='😊')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    fingerprint = db.Column(db.Text, default='{}')

    posts        = db.relationship('Post', backref='author_user', lazy='dynamic',
                                   foreign_keys='Post.author_id')
    comments     = db.relationship('Comment', backref='author_user', lazy='dynamic')
    notifications= db.relationship('Notification', backref='recipient', lazy='dynamic',
                                   foreign_keys='Notification.user_id')

class Follow(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('follower_id', 'followed_id'),)

class Post(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    author_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # None = seed post
    text       = db.Column(db.String(500), nullable=False)
    topic      = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # seed posts have these filled from SEED_POSTS
    seed_author = db.Column(db.String(80))
    seed_avatar = db.Column(db.String(10))
    seed_likes  = db.Column(db.Integer, default=0)

    # media extensions
    post_type   = db.Column(db.String(20), default='text')   # text | image | poll | link
    image_url   = db.Column(db.String(300))                  # for image posts
    link_url    = db.Column(db.String(300))                  # for link posts
    link_title  = db.Column(db.String(200))
    link_domain = db.Column(db.String(100))
    poll_question   = db.Column(db.String(200))              # for poll posts
    poll_options    = db.Column(db.Text)                     # JSON list of option strings
    poll_votes      = db.Column(db.Text, default='{}')       # JSON {option_index: count}

    comments   = db.relationship('Comment', backref='post', lazy='dynamic',
                                  cascade='all, delete-orphan')
    likes      = db.relationship('PostLike', backref='post', lazy='dynamic',
                                  cascade='all, delete-orphan')

class PostLike(db.Model):
    id      = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('post_id', 'user_id'),)

class Comment(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text       = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # recipient
    actor_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)   # who triggered it
    ntype      = db.Column(db.String(30))   # like, comment, follow
    post_id    = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    read       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Event(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_type = db.Column(db.String(50))
    target     = db.Column(db.String(200))
    value      = db.Column(db.String(500))
    ts         = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------------------------------------------------------------------
# Seed data — stored in DB on first run
# ---------------------------------------------------------------------------

SEED_POSTS = [
    # ── text posts ────────────────────────────────────────────────────────────
    {"type": "text", "topic": "Gaming",  "author": "xX_ProGamer_Xx",  "avatar": "🎮",
     "text": "Just hit Diamond rank in Valorant after 200 hours 🔥 grind never stops", "likes": 342},
    {"type": "text", "topic": "Music",   "author": "BeatsByMaya",      "avatar": "🎵",
     "text": "New Taylor Swift album dropped and I haven't slept in 48h, no regrets 😭", "likes": 891},
    {"type": "text", "topic": "Sport",   "author": "FootballFanatic",  "avatar": "⚽",
     "text": "Champions League final was INSANE tonight. Best game in years!!", "likes": 1203},
    {"type": "text", "topic": "Tech",    "author": "CodeNerd42",        "avatar": "💻",
     "text": "Built my first app with Python today. Honestly it's easier than I thought 🐍", "likes": 445},
    {"type": "text", "topic": "Fashion", "author": "StyleByJess",       "avatar": "👗",
     "text": "Y2K fashion is officially back and I am HERE for it 💅 thrift store haul incoming", "likes": 674},
    {"type": "text", "topic": "Gaming",  "author": "NightOwlGamer",    "avatar": "🎮",
     "text": "Minecraft or Roblox? Hot take: Minecraft still wins in 2025, change my mind", "likes": 512},
    {"type": "text", "topic": "Food",    "author": "FoodieKing",        "avatar": "🍕",
     "text": "Made homemade ramen from scratch, took 6 hours but totally worth it 🍜", "likes": 788},
    {"type": "text", "topic": "Travel",  "author": "WanderlustKid",    "avatar": "✈️",
     "text": "Tokyo in spring is literally a dream. Cherry blossoms everywhere 🌸", "likes": 1567},
    {"type": "text", "topic": "Sport",   "author": "GymRat_Alex",       "avatar": "💪",
     "text": "Day 100 of working out every day. Body transformation pics in comments 💪", "likes": 923},
    {"type": "text", "topic": "Music",   "author": "VinylCollector",   "avatar": "🎵",
     "text": "Found an original 1979 Pink Floyd record at a flea market for €2. Best day ever", "likes": 334},
    {"type": "text", "topic": "Tech",    "author": "AIEnthusiast",      "avatar": "🤖",
     "text": "ChatGPT just helped me write my entire history essay lol, is this cheating?", "likes": 2341},
    {"type": "text", "topic": "Fashion", "author": "StreetStylePro",   "avatar": "👟",
     "text": "Air Force 1s or New Balance 550? Can't decide which ones to cop 👀", "likes": 445},
    {"type": "text", "topic": "Food",    "author": "BakingQueen",       "avatar": "🧁",
     "text": "Accidentally put salt instead of sugar in my cookies 🤡 they're in the bin", "likes": 2890},
    {"type": "text", "topic": "Travel",  "author": "BackpackerBenny",  "avatar": "🎒",
     "text": "Booked a one-way ticket to Lisbon. No plan, no hotel, just vibes 🫡", "likes": 3100},
    {"type": "text", "topic": "Tech",    "author": "DevDave",           "avatar": "🧑",
     "text": "My CSS finally worked on the first try. I will never experience this feeling again", "likes": 5700},
    {"type": "text", "topic": "Sport",   "author": "RunnerGirl",        "avatar": "🏃",
     "text": "Just ran my first marathon!! 42km in 4h12m — I literally cried at the finish line 😭🏅", "likes": 4200},
    {"type": "text", "topic": "Gaming",  "author": "RetroGamerPaul",   "avatar": "🕹️",
     "text": "Unpopular opinion: GTA San Andreas > GTA V. That story was peak, no debate", "likes": 987},
    {"type": "text", "topic": "Music",   "author": "ChillBeats99",      "avatar": "🎧",
     "text": "If you're studying right now, lofi hip hop is literally a cheat code 🧠📚", "likes": 1420},
    {"type": "text", "topic": "Food",    "author": "VeganVictor",       "avatar": "🥗",
     "text": "Made a vegan burger that actually tastes like meat. My non-vegan flatmate ate 3. 👀", "likes": 2100},
    {"type": "text", "topic": "Fashion", "author": "ThriftQueen",       "avatar": "🛍️",
     "text": "€8 for this vintage Levi's jacket at the thrift store. Retail is a scam fr 🙏", "likes": 3300},
    {"type": "text", "topic": "Travel",  "author": "SoloTravelerSara",  "avatar": "🗺️",
     "text": "Traveling solo as a woman is the best thing I've ever done. 10/10 recommend 🌍", "likes": 4800},
    {"type": "text", "topic": "Gaming",  "author": "SpeedrunnerMike",  "avatar": "⚡",
     "text": "New personal best: finished Celeste in 47 minutes. The grind was real 🍓", "likes": 760},
    {"type": "text", "topic": "Tech",    "author": "PrivacyNerd",       "avatar": "🔒",
     "text": "Reminder that every app on your phone is tracking your location, even when closed. Delete what you don't use.", "likes": 6100},
    {"type": "text", "topic": "Music",   "author": "FestivalFreak",     "avatar": "🎪",
     "text": "Glastonbury lineup dropped and I'm already crying at the ticket prices 😭 still buying them tho", "likes": 1850},
    {"type": "text", "topic": "Sport",   "author": "BasketballBro",     "avatar": "🏀",
     "text": "LeBron at 40 still dropping 30-point games. Humans aren't supposed to do that", "likes": 2900},

    # ── image posts ───────────────────────────────────────────────────────────
    {"type": "image", "topic": "Travel", "author": "WanderlustKid", "avatar": "✈️",
     "text": "Santorini sunsets hit different 🌅",
     "image_url": "https://images.unsplash.com/photo-1570077188670-e3a8d69ac5ff?w=600&q=80",
     "likes": 2840},
    {"type": "image", "topic": "Food", "author": "FoodieKing", "avatar": "🍕",
     "text": "Sunday brunch energy 🥞☕",
     "image_url": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&q=80",
     "likes": 1340},
    {"type": "image", "topic": "Sport", "author": "GymRat_Alex", "avatar": "💪",
     "text": "Before vs. after — 6 months of consistent training. Trust the process 💯",
     "image_url": "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600&q=80",
     "likes": 5120},
    {"type": "image", "topic": "Fashion", "author": "StyleByJess", "avatar": "👗",
     "text": "OOTD: thrifted everything for under €15 💅 links in bio",
     "image_url": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=600&q=80",
     "likes": 1870},
    {"type": "image", "topic": "Gaming", "author": "xX_ProGamer_Xx", "avatar": "🎮",
     "text": "New setup just dropped 🖥️ finally upgraded from my 2015 potato PC",
     "image_url": "https://images.unsplash.com/photo-1593640495253-23196b27a87f?w=600&q=80",
     "likes": 2290},
    {"type": "image", "topic": "Travel", "author": "BackpackerBenny", "avatar": "🎒",
     "text": "Three weeks in Southeast Asia for under €900. Here's how 🧵",
     "image_url": "https://images.unsplash.com/photo-1552465011-b4e21bf6e79a?w=600&q=80",
     "likes": 4100},
    {"type": "image", "topic": "Food", "author": "BakingQueen", "avatar": "🧁",
     "text": "Redemption arc: today's batch came out PERFECT 🍪✨",
     "image_url": "https://images.unsplash.com/photo-1499636136210-6f4ee915583e?w=600&q=80",
     "likes": 3560},
    {"type": "image", "topic": "Music", "author": "VinylCollector", "avatar": "🎵",
     "text": "The collection is growing 👀 any recs for what to add next?",
     "image_url": "https://images.unsplash.com/photo-1603481546238-487240415921?w=600&q=80",
     "likes": 1230},
    {"type": "image", "topic": "Tech", "author": "DevDave", "avatar": "🧑",
     "text": "My home office setup after 2 years of iteration. Still not satisfied honestly",
     "image_url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600&q=80",
     "likes": 2770},

    # ── poll posts ────────────────────────────────────────────────────────────
    {"type": "poll", "topic": "Gaming", "author": "NightOwlGamer", "avatar": "🎮",
     "text": "The debate ends here. VOTE NOW 👇",
     "poll_question": "Best gaming platform?",
     "poll_options": ["PC Master Race 🖥️", "PlayStation 🎮", "Xbox 🟩", "Nintendo Switch 🕹️"],
     "poll_votes": [4821, 3104, 1893, 2560],
     "likes": 892},
    {"type": "poll", "topic": "Food", "author": "FoodieKing", "avatar": "🍕",
     "text": "I will not rest until this is settled 🍍",
     "poll_question": "Pineapple on pizza?",
     "poll_options": ["Absolutely not 🤢", "Yes, it's good 🍍", "Depends on the rest", "I don't care"],
     "poll_votes": [6230, 2140, 890, 410],
     "likes": 3400},
    {"type": "poll", "topic": "Music", "author": "BeatsByMaya", "avatar": "🎵",
     "text": "Tell me who you are based on your answer 👇",
     "poll_question": "How do you listen to music?",
     "poll_options": ["Spotify 🟢", "Apple Music 🍎", "YouTube", "Vinyl / CDs 📀"],
     "poll_votes": [8900, 3200, 2100, 450],
     "likes": 1670},
    {"type": "poll", "topic": "Tech", "author": "AIEnthusiast", "avatar": "🤖",
     "text": "No wrong answers (there are wrong answers)",
     "poll_question": "Best programming language for beginners?",
     "poll_options": ["Python 🐍", "JavaScript", "Java ☕", "C++ 💀"],
     "poll_votes": [5400, 3100, 980, 230],
     "likes": 2100},
    {"type": "poll", "topic": "Sport", "author": "FootballFanatic", "avatar": "⚽",
     "text": "Drop your answer, no cowards 👇",
     "poll_question": "GOAT of football?",
     "poll_options": ["Messi 🐐", "Ronaldo", "Ronaldinho", "Someone else"],
     "poll_votes": [7800, 5600, 1200, 900],
     "likes": 4500},

    # ── link posts ────────────────────────────────────────────────────────────
    {"type": "link", "topic": "Tech", "author": "PrivacyNerd", "avatar": "🔒",
     "text": "Everyone should read this. Bookmarked it immediately 👇",
     "link_url": "https://www.eff.org/issues/privacy",
     "link_title": "Privacy | Electronic Frontier Foundation",
     "link_domain": "eff.org",
     "likes": 1890},
    {"type": "link", "topic": "Tech", "author": "CodeNerd42", "avatar": "💻",
     "text": "The best free resource to learn web development. Zero excuses now 🚀",
     "link_url": "https://www.theodinproject.com",
     "link_title": "The Odin Project — Your Career in Web Development Starts Here",
     "link_domain": "theodinproject.com",
     "likes": 3200},
    {"type": "link", "topic": "Music", "author": "ChillBeats99", "avatar": "🎧",
     "text": "My current favourite playlist for deep work sessions 🎵",
     "link_url": "https://open.spotify.com",
     "link_title": "lofi hip hop radio - beats to relax/study to · Spotify",
     "link_domain": "open.spotify.com",
     "likes": 2100},
    {"type": "link", "topic": "Travel", "author": "SoloTravelerSara", "avatar": "🗺️",
     "text": "How I planned a 3-week Europe trip for under €1000 — the full breakdown",
     "link_url": "https://www.lonelyplanet.com",
     "link_title": "Budget Europe Travel Guide 2025 · Lonely Planet",
     "link_domain": "lonelyplanet.com",
     "likes": 2770},
]
TOPIC_EMOJIS = {
    "Gaming": "🎮", "Music": "🎵", "Sport": "⚽", "Tech": "💻",
    "Fashion": "👗", "Food": "🍕", "Travel": "✈️", "Other": "💬",
}

AVATAR_OPTIONS = ["😊","😎","🤩","🥳","😄","🧑","👦","👧","🦸","🧙","🐱","🐶","🦊","🐸","🦁"]

def seed_posts():
    if Post.query.count() == 0:
        for s in SEED_POSTS:
            ptype = s.get('type', 'text')
            p = Post(
                author_id=None,
                text=s['text'],
                topic=s['topic'],
                seed_author=s['author'],
                seed_avatar=s['avatar'],
                seed_likes=s.get('likes', 0),
                post_type=ptype,
                image_url=s.get('image_url'),
                link_url=s.get('link_url'),
                link_title=s.get('link_title'),
                link_domain=s.get('link_domain'),
                poll_question=s.get('poll_question'),
                poll_options=json.dumps(s['poll_options']) if 'poll_options' in s else None,
                poll_votes=json.dumps(
                    {str(i): v for i, v in enumerate(s['poll_votes'])}
                ) if 'poll_votes' in s else '{}',
            )
            db.session.add(p)
        db.session.commit()

# ---------------------------------------------------------------------------
# Helper: current user
# ---------------------------------------------------------------------------

def current_user():
    if 'user_id' not in session:
        return None
    return User.query.get(session['user_id'])

def unread_notification_count(user_id):
    return Notification.query.filter_by(user_id=user_id, read=False).count()

# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('feed'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        email      = request.form.get('email', '').strip()
        full_name  = request.form.get('full_name', '').strip()
        age        = request.form.get('age', '').strip()
        avatar     = request.form.get('avatar', '😊')

        if not username or not email:
            error = "Username and email are required."
        elif User.query.filter_by(username=username).first():
            error = "Username already taken."
        elif User.query.filter_by(email=email).first():
            error = "Email already registered."
        else:
            user = User(username=username, email=email, full_name=full_name,
                        age=int(age) if age.isdigit() else None,
                        avatar_emoji=avatar if avatar in AVATAR_OPTIONS else '😊')
            db.session.add(user)
            db.session.commit()
            session['user_id']  = user.id
            session['username'] = user.username
            collect_ip(user)
            return redirect(url_for('feed'))

    return render_template('register.html', error=error, avatars=AVATAR_OPTIONS)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username).first()
        if user:
            session['user_id']  = user.id
            session['username'] = user.username
            collect_ip(user)
            return redirect(url_for('feed'))
        else:
            error = "Account not found. Please register first."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------------------------------------------------------------------------
# Routes — Feed
# ---------------------------------------------------------------------------

def compute_interest_scores(user_id):
    """Return a dict {topic: score} built from the user's tracked events."""
    events = Event.query.filter_by(user_id=user_id).all()
    scores = {}
    for e in events:
        topic = None
        weight = 0
        if e.event_type == 'like':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                topic, weight = post.topic or 'Other', 3
        elif e.event_type == 'comment':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                topic, weight = post.topic or 'Other', 4
        elif e.event_type == 'poll_vote':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                topic, weight = post.topic or 'Other', 2
        elif e.event_type == 'view':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                secs = float(e.value) if e.value else 0
                topic = post.topic or 'Other'
                weight = 2 if secs >= 5 else 1
        elif e.event_type == 'topic_click':
            topic  = e.target
            weight = 2
        elif e.event_type == 'new_post':
            topic, weight = e.value or 'Other', 3
        if topic:
            scores[topic] = scores.get(topic, 0) + weight
    return scores

def rank_posts_for_user(posts, interest_scores):
    """
    Score each post, then sort descending.
    New posts from followed users get a recency bonus.
    A small random jitter keeps the feed from feeling completely static.
    Returns (ranked_posts, top_topics) where top_topics is the top-3 list.
    """
    import random, math
    total = sum(interest_scores.values()) or 1
    # normalise scores to 0-1
    norm = {t: s / total for t, s in interest_scores.items()}

    def post_score(p):
        base       = norm.get(p.topic or 'Other', 0) * 100
        # slight recency boost (decay over ~7 days)
        age_hours  = (datetime.utcnow() - p.created_at).total_seconds() / 3600
        recency    = math.exp(-age_hours / 168)   # half-life ~7 days
        jitter     = random.uniform(0, 8)
        return base * 0.7 + recency * 15 + jitter

    has_signal = bool(interest_scores)
    if has_signal:
        ranked = sorted(posts, key=post_score, reverse=True)
    else:
        ranked = posts   # chronological for new users

    top_topics = sorted(interest_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    return ranked, top_topics


@app.route('/feed')
def feed():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    me = current_user()

    # fetch all posts (personalisation happens in Python, not SQL)
    all_posts = Post.query.order_by(Post.created_at.desc()).all()

    interest_scores            = compute_interest_scores(me.id)
    posts, top_topics          = rank_posts_for_user(all_posts, interest_scores)
    is_personalised            = bool(interest_scores)

    # which post ids has the current user liked?
    liked_ids = {pl.post_id for pl in PostLike.query.filter_by(user_id=me.id).all()}

    # suggested users: not yet followed, not self, limit 5
    followed_ids = {f.followed_id for f in Follow.query.filter_by(follower_id=me.id).all()}
    suggested = User.query.filter(
        User.id != me.id,
        ~User.id.in_(followed_ids)
    ).order_by(db.func.random()).limit(5).all()

    notif_count = unread_notification_count(me.id)

    return render_template('feed.html',
                           me=me,
                           posts=posts,
                           liked_ids=liked_ids,
                           suggested=suggested,
                           notif_count=notif_count,
                           topic_emojis=TOPIC_EMOJIS,
                           topics=list(TOPIC_EMOJIS.keys()),
                           is_personalised=is_personalised,
                           top_topics=top_topics)

# ---------------------------------------------------------------------------
# Routes — Posts
# ---------------------------------------------------------------------------

@app.route('/post/new', methods=['POST'])
def new_post():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    text  = request.form.get('text', '').strip()
    topic = request.form.get('topic', 'Other').strip()
    if text:
        p = Post(author_id=session['user_id'], text=text[:500], topic=topic)
        db.session.add(p)
        db.session.commit()
        # track
        ev = Event(user_id=session['user_id'], event_type='new_post',
                   target=str(p.id), value=topic)
        db.session.add(ev)
        db.session.commit()
    return redirect(url_for('feed'))

@app.route('/post/<int:post_id>/like', methods=['POST'])
def like_post(post_id):
    if 'user_id' not in session:
        return jsonify({'ok': False}), 401
    me   = current_user()
    post = Post.query.get_or_404(post_id)
    existing = PostLike.query.filter_by(post_id=post_id, user_id=me.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        liked = False
    else:
        db.session.add(PostLike(post_id=post_id, user_id=me.id))
        db.session.commit()
        liked = True
        # notify post author (if real user, not self)
        if post.author_id and post.author_id != me.id:
            notif = Notification(user_id=post.author_id, actor_id=me.id,
                                 ntype='like', post_id=post_id)
            db.session.add(notif)
            db.session.commit()
        # track interest
        ev = Event(user_id=me.id, event_type='like', target=str(post_id),
                   value=post.topic or '')
        db.session.add(ev)
        db.session.commit()

    total = PostLike.query.filter_by(post_id=post_id).count()
    if post.seed_likes:
        total += post.seed_likes
    return jsonify({'ok': True, 'liked': liked, 'count': total})

@app.route('/post/<int:post_id>/vote', methods=['POST'])
def vote_poll(post_id):
    if 'user_id' not in session:
        return jsonify({'ok': False}), 401
    post = Post.query.get_or_404(post_id)
    if post.post_type != 'poll':
        return jsonify({'ok': False, 'error': 'not a poll'})
    option_index = request.get_json(silent=True, force=True).get('option')
    if option_index is None:
        return jsonify({'ok': False})
    votes = json.loads(post.poll_votes or '{}')
    key = str(option_index)
    votes[key] = votes.get(key, 0) + 1
    post.poll_votes = json.dumps(votes)
    db.session.commit()
    # track
    ev = Event(user_id=session['user_id'], event_type='poll_vote',
               target=str(post_id), value=str(option_index))
    db.session.add(ev)
    db.session.commit()
    total = sum(votes.values())
    percentages = {k: round(v / total * 100) if total else 0 for k, v in votes.items()}
    return jsonify({'ok': True, 'votes': votes, 'percentages': percentages, 'total': total})


def add_comment(post_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    me   = current_user()
    post = Post.query.get_or_404(post_id)
    text = request.form.get('text', '').strip()
    if text:
        c = Comment(post_id=post_id, author_id=me.id, text=text[:300])
        db.session.add(c)
        db.session.commit()
        # notify post author
        if post.author_id and post.author_id != me.id:
            notif = Notification(user_id=post.author_id, actor_id=me.id,
                                 ntype='comment', post_id=post_id)
            db.session.add(notif)
            db.session.commit()
        # track
        ev = Event(user_id=me.id, event_type='comment', target=str(post_id),
                   value=post.topic or '')
        db.session.add(ev)
        db.session.commit()
    return redirect(url_for('feed') + f'#post-{post_id}')

# ---------------------------------------------------------------------------
# Routes — Follow
# ---------------------------------------------------------------------------

@app.route('/follow/<int:user_id>', methods=['POST'])
def follow(user_id):
    if 'user_id' not in session:
        return jsonify({'ok': False}), 401
    me = current_user()
    if user_id == me.id:
        return jsonify({'ok': False, 'error': "Can't follow yourself"})
    existing = Follow.query.filter_by(follower_id=me.id, followed_id=user_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        following = False
    else:
        db.session.add(Follow(follower_id=me.id, followed_id=user_id))
        db.session.commit()
        following = True
        # notify
        notif = Notification(user_id=user_id, actor_id=me.id, ntype='follow')
        db.session.add(notif)
        db.session.commit()
        # track
        ev = Event(user_id=me.id, event_type='follow', target=str(user_id), value='')
        db.session.add(ev)
        db.session.commit()

    target = User.query.get(user_id)
    followers = Follow.query.filter_by(followed_id=user_id).count()
    return jsonify({'ok': True, 'following': following, 'followers': followers,
                    'username': target.username})

# ---------------------------------------------------------------------------
# Routes — User profiles
# ---------------------------------------------------------------------------

@app.route('/u/<username>')
def user_profile(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    me        = current_user()
    target    = User.query.filter_by(username=username).first_or_404()
    posts     = Post.query.filter_by(author_id=target.id).order_by(Post.created_at.desc()).all()
    liked_ids = {pl.post_id for pl in PostLike.query.filter_by(user_id=me.id).all()}
    followers = Follow.query.filter_by(followed_id=target.id).count()
    following_count = Follow.query.filter_by(follower_id=target.id).count()
    is_following = bool(Follow.query.filter_by(follower_id=me.id, followed_id=target.id).first())
    notif_count  = unread_notification_count(me.id)

    # track profile view
    if target.id != me.id:
        ev = Event(user_id=me.id, event_type='profile_view', target=str(target.id),
                   value=username)
        db.session.add(ev)
        db.session.commit()

    return render_template('user_profile.html',
                           me=me, target=target, posts=posts,
                           liked_ids=liked_ids, followers=followers,
                           following_count=following_count,
                           is_following=is_following,
                           notif_count=notif_count,
                           topic_emojis=TOPIC_EMOJIS)

@app.route('/u/<username>/edit', methods=['GET', 'POST'])
def edit_profile(username):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    me = current_user()
    if me.username != username:
        return redirect(url_for('user_profile', username=username))

    if request.method == 'POST':
        me.full_name   = request.form.get('full_name', '').strip()
        me.bio         = request.form.get('bio', '').strip()[:300]
        avatar         = request.form.get('avatar', me.avatar_emoji)
        if avatar in AVATAR_OPTIONS:
            me.avatar_emoji = avatar
        db.session.commit()
        return redirect(url_for('user_profile', username=me.username))

    return render_template('edit_profile.html', me=me, avatars=AVATAR_OPTIONS,
                           notif_count=unread_notification_count(me.id))

# ---------------------------------------------------------------------------
# Routes — Notifications
# ---------------------------------------------------------------------------

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    me = current_user()
    notifs = (Notification.query
              .filter_by(user_id=me.id)
              .order_by(Notification.created_at.desc())
              .limit(50).all())
    # mark all read
    Notification.query.filter_by(user_id=me.id, read=False).update({'read': True})
    db.session.commit()

    # enrich with actor info
    enriched = []
    for n in notifs:
        actor = User.query.get(n.actor_id) if n.actor_id else None
        post  = Post.query.get(n.post_id)  if n.post_id  else None
        enriched.append({'n': n, 'actor': actor, 'post': post})

    return render_template('notifications.html', me=me, enriched=enriched,
                           notif_count=0)

# ---------------------------------------------------------------------------
# Routes — Data profile (the reveal page)
# ---------------------------------------------------------------------------

@app.route('/mydata')
def mydata():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    me     = current_user()
    events = Event.query.filter_by(user_id=me.id).all()

    topic_counts = {}
    liked_post_ids = set()
    total_time = 0

    for e in events:
        if e.event_type == 'like':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                liked_post_ids.add(post.id)
                t = post.topic or 'Other'
                topic_counts[t] = topic_counts.get(t, 0) + 3
        elif e.event_type == 'view':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                secs = float(e.value) if e.value else 0
                total_time += secs
                t = post.topic or 'Other'
                topic_counts[t] = topic_counts.get(t, 0) + (1 if secs < 5 else 2)
        elif e.event_type == 'comment':
            post = Post.query.get(int(e.target)) if e.target.isdigit() else None
            if post:
                t = post.topic or 'Other'
                topic_counts[t] = topic_counts.get(t, 0) + 2
        elif e.event_type == 'follow':
            topic_counts['Social'] = topic_counts.get('Social', 0) + 1

    liked_posts  = [Post.query.get(pid) for pid in liked_post_ids if Post.query.get(pid)]
    sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
    fingerprint   = json.loads(me.fingerprint) if me.fingerprint else {}

    followers_list = (User.query
                      .join(Follow, Follow.follower_id == User.id)
                      .filter(Follow.followed_id == me.id).all())
    following_list = (User.query
                      .join(Follow, Follow.followed_id == User.id)
                      .filter(Follow.follower_id == me.id).all())

    notif_count = unread_notification_count(me.id)

    return render_template('mydata.html',
                           me=me,
                           events=events,
                           sorted_topics=sorted_topics,
                           liked_posts=liked_posts,
                           total_time=round(total_time),
                           fingerprint=fingerprint,
                           event_count=len(events),
                           followers_list=followers_list,
                           following_list=following_list,
                           notif_count=notif_count)

# ---------------------------------------------------------------------------
# Tracking API
# ---------------------------------------------------------------------------

@app.route('/track', methods=['POST'])
def track():
    if 'user_id' not in session:
        return jsonify({'ok': False}), 401
    data = request.get_json(silent=True) or {}
    event_type = data.get('type')
    target     = str(data.get('target', ''))
    value      = str(data.get('value', ''))
    if event_type:
        db.session.add(Event(user_id=session['user_id'],
                             event_type=event_type, target=target, value=value))
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/fingerprint', methods=['POST'])
def fingerprint_route():
    if 'user_id' not in session:
        return jsonify({'ok': False}), 401
    data = request.get_json(silent=True) or {}
    user = current_user()
    if user:
        fp = json.loads(user.fingerprint) if user.fingerprint else {}
        fp.update(data)
        user.fingerprint = json.dumps(fp)
        db.session.commit()
    return jsonify({'ok': True})

def collect_ip(user):
    """Collect IP + basic geo info and store in fingerprint."""
    # X-Forwarded-For is set by Railway's proxy
    forwarded = request.headers.get('X-Forwarded-For', '')
    ip = forwarded.split(',')[0].strip() if forwarded else request.remote_addr

    fp = json.loads(user.fingerprint) if user.fingerprint else {}

    # Store raw IP and every IP seen across sessions
    fp['ip_address'] = ip
    seen = fp.get('ip_addresses_seen', [])
    if ip not in seen:
        seen.append(ip)
    fp['ip_addresses_seen'] = seen

    # Rough geo lookup via free ip-api.com (no key needed, 45 req/min)
    try:
        import urllib.request as urlreq
        with urlreq.urlopen(f'http://ip-api.com/json/{ip}?fields=country,regionName,city,isp,org,lat,lon', timeout=3) as r:
            geo = json.loads(r.read().decode())
        if geo.get('city'):
            fp['location_city']    = geo.get('city', '—')
            fp['location_region']  = geo.get('regionName', '—')
            fp['location_country'] = geo.get('country', '—')
            fp['location_isp']     = geo.get('isp', '—')
            fp['location_org']     = geo.get('org', '—')
            fp['location_lat_lon'] = f"{geo.get('lat')}, {geo.get('lon')}"
    except Exception:
        pass  # geo lookup failed silently — IP is still stored

    user.fingerprint = json.dumps(fp)
    db.session.commit()

@app.route('/notifications/count')
def notif_count_api():
    if 'user_id' not in session:
        return jsonify({'count': 0})
    return jsonify({'count': unread_notification_count(session['user_id'])})

# ---------------------------------------------------------------------------
# DB init — runs on startup whether via gunicorn or python app.py
# ---------------------------------------------------------------------------

def init_db():
    os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
    with app.app_context():
        db.create_all()
        seed_posts()

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
