from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import re
import os

# Get the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)

# Use absolute path for database
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "artist_market.db")}'
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.Text)
    avatar_url = db.Column(db.String(200))
    is_artist = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    commissions = db.relationship('Commission', backref='artist', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float)
    is_for_sale = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Commission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    artist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Utilities
def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_price(price):
    try:
        p = float(price)
        return 0 < p <= 999999
    except:
        return False

def validate_rating(rating):
    try:
        r = int(rating)
        return 1 <= r <= 5
    except:
        return False

# Routes
@app.route('/')
def homepage():
    try:
        page = request.args.get('page', 1, type=int)
        sort = request.args.get('sort', 'recent')
        
        query = Post.query
        if sort == 'price_low':
            query = query.filter(Post.price.isnot(None)).order_by(Post.price.asc())
        elif sort == 'price_high':
            query = query.filter(Post.price.isnot(None)).order_by(Post.price.desc())
        else:
            query = query.order_by(Post.created_at.desc())
        
        posts = query.paginate(page=page, per_page=12)
        return render_template('homepage.html', posts=posts, sort=sort)
    except Exception as e:
        return render_template('error.html', error='Error loading posts'), 500

@app.route('/search')
def search():
    try:
        query = request.args.get('q', '').strip()[:100]
        page = request.args.get('page', 1, type=int)
        if not query or len(query) < 2:
            return render_template('search.html', posts=None, users=None, query='')
        
        posts = Post.query.filter(Post.title.ilike(f'%{query}%') | Post.description.ilike(f'%{query}%')).paginate(page=page, per_page=12)
        users = User.query.filter(User.username.ilike(f'%{query}%')).limit(10).all()
        return render_template('search.html', posts=posts, users=users, query=query)
    except Exception as e:
        return render_template('error.html', error='Search error'), 500

@app.route('/profile/<username>')
def profile(username):
    try:
        user = User.query.filter_by(username=username).first_or_404()
        page = request.args.get('page', 1, type=int)
        posts = Post.query.filter_by(user_id=user.id).paginate(page=page, per_page=10)
        commissions = Commission.query.filter_by(artist_id=user.id).all() if user.is_artist else []
        return render_template('profile.html', user=user, posts=posts, commissions=commissions)
    except Exception as e:
        return render_template('error.html', error='User not found'), 404

@app.route('/api/profile/edit', methods=['POST'])
@login_required
@csrf.exempt
def edit_profile():
    try:
        user = get_current_user()
        data = request.get_json()
        if 'bio' in data:
            user.bio = data['bio'][:500]
        if 'avatar_url' in data:
            user.avatar_url = data['avatar_url'][:500]
        if 'is_artist' in data:
            user.is_artist = bool(data['is_artist'])
        db.session.commit()
        return jsonify({'success': True, 'message': 'Profile updated'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/register', methods=['POST'])
@csrf.exempt
def register():
    try:
        data = request.get_json()
        if not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing required fields'}), 400
        if len(data['username']) < 3 or len(data['username']) > 80:
            return jsonify({'error': 'Username must be 3-80 characters'}), 400
        if not validate_email(data['email']):
            return jsonify({'error': 'Invalid email format'}), 400
        if len(data['password']) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already registered'}), 400
        user = User(username=data['username'], email=data['email'], password=generate_password_hash(data['password']))
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return jsonify({'success': True, 'message': 'Registration successful'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/login', methods=['POST'])
@csrf.exempt
def login():
    try:
        data = request.get_json()
        if not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Missing username or password'}), 400
        user = User.query.filter_by(username=data['username']).first()
        if user and check_password_hash(user.password, data['password']):
            session['user_id'] = user.id
            return jsonify({'success': True, 'message': 'Login successful'}), 200
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('homepage'))

@app.route('/api/posts', methods=['POST'])
@login_required
@csrf.exempt
def create_post():
    try:
        user = get_current_user()
        data = request.get_json()
        if not data.get('title') or not data.get('image_url'):
            return jsonify({'error': 'Title and image required'}), 400
        if len(data['title']) > 200:
            return jsonify({'error': 'Title too long'}), 400
        if data.get('price') and not validate_price(data['price']):
            return jsonify({'error': 'Invalid price'}), 400
        post = Post(
            title=data['title'],
            description=data.get('description', '')[:1000],
            image_url=data['image_url'][:500],
            price=float(data.get('price')) if data.get('price') else None,
            is_for_sale=bool(data.get('is_for_sale', False)),
            user_id=user.id
        )
        db.session.add(post)
        db.session.commit()
        return jsonify({'success': True, 'post_id': post.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
@login_required
@csrf.exempt
def delete_post(post_id):
    try:
        user = get_current_user()
        post = Post.query.get_or_404(post_id)
        if post.user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        db.session.delete(post)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Post deleted'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/posts/<int:post_id>', methods=['PUT'])
@login_required
@csrf.exempt
def update_post(post_id):
    try:
        user = get_current_user()
        post = Post.query.get_or_404(post_id)
        if post.user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        data = request.get_json()
        if 'title' in data:
            post.title = data['title'][:200]
        if 'description' in data:
            post.description = data['description'][:1000]
        if 'price' in data and not validate_price(data['price']):
            return jsonify({'error': 'Invalid price'}), 400
        if 'price' in data:
            post.price = float(data['price']) if data['price'] else None
        if 'is_for_sale' in data:
            post.is_for_sale = bool(data['is_for_sale'])
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/favorites/<int:post_id>', methods=['POST'])
@login_required
@csrf.exempt
def add_favorite(post_id):
    try:
        user = get_current_user()
        post = Post.query.get_or_404(post_id)
        fav = Favorite.query.filter_by(user_id=user.id, post_id=post_id).first()
        if fav:
            return jsonify({'error': 'Already favorited'}), 400
        favorite = Favorite(user_id=user.id, post_id=post_id)
        db.session.add(favorite)
        db.session.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/favorites/<int:post_id>', methods=['DELETE'])
@login_required
@csrf.exempt
def remove_favorite(post_id):
    try:
        user = get_current_user()
        fav = Favorite.query.filter_by(user_id=user.id, post_id=post_id).first_or_404()
        db.session.delete(fav)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews/<int:post_id>', methods=['POST'])
@login_required
@csrf.exempt
def create_review(post_id):
    try:
        user = get_current_user()
        data = request.get_json()
        if not validate_rating(data.get('rating')):
            return jsonify({'error': 'Rating must be 1-5'}), 400
        review = Review(
            rating=int(data['rating']),
            comment=data.get('comment', '')[:500],
            user_id=user.id,
            post_id=post_id
        )
        db.session.add(review)
        db.session.commit()
        return jsonify({'success': True}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/<int:post_id>', methods=['POST'])
@login_required
@csrf.exempt
def create_order(post_id):
    try:
        user = get_current_user()
        post = Post.query.get_or_404(post_id)
        if not post.is_for_sale:
            return jsonify({'error': 'Post not for sale'}), 400
        if post.user_id == user.id:
            return jsonify({'error': 'Cannot buy own post'}), 400
        order = Order(buyer_id=user.id, post_id=post_id, price=post.price)
        db.session.add(order)
        db.session.commit()
        return jsonify({'success': True, 'order_id': order.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/commissions', methods=['POST'])
@login_required
@csrf.exempt
def create_commission():
    try:
        user = get_current_user()
        if not user.is_artist:
            return jsonify({'error': 'Only artists can create commissions'}), 403
        data = request.get_json()
        if not data.get('title') or not validate_price(data.get('price')):
            return jsonify({'error': 'Title and valid price required'}), 400
        commission = Commission(
            title=data['title'][:200],
            description=data.get('description', '')[:1000],
            price=float(data['price']),
            artist_id=user.id
        )
        db.session.add(commission)
        db.session.commit()
        return jsonify({'success': True, 'commission_id': commission.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/commissions/<int:commission_id>', methods=['DELETE'])
@login_required
@csrf.exempt
def delete_commission(commission_id):
    try:
        user = get_current_user()
        commission = Commission.query.get_or_404(commission_id)
        if commission.artist_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        db.session.delete(commission)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/register-page')
def register_page():
    return render_template('register.html')

@app.route('/login-page')
def login_page():
    return render_template('login.html')

@app.route('/seed')
def seed_data():
    """Create demo data for testing - remove in production"""
    try:
        demo_user = User.query.filter_by(username='demo_artist').first()
        if not demo_user:
            demo_user = User(
                username='demo_artist',
                email='demo@example.com',
                password=generate_password_hash('password123'),
                bio='Demo artist showcasing the marketplace',
                is_artist=True
            )
            db.session.add(demo_user)
            db.session.commit()

        if Post.query.count() == 0:
            sample_posts = [
                Post(
                    title='Abstract Watercolor Series',
                    description='Beautiful abstract watercolor painting with flowing colors and organic shapes.',
                    image_url='https://images.unsplash.com/photo-1561214115-6d2f1b0609fa?w=400&h=300&fit=crop',
                    price=150.00,
                    is_for_sale=True,
                    user_id=demo_user.id
                ),
                Post(
                    title='Digital Portrait Commission',
                    description='Custom digital portrait of your favorite characters or people.',
                    image_url='https://images.unsplash.com/photo-1561070791-2526d30994b5?w=400&h=300&fit=crop',
                    price=75.00,
                    is_for_sale=True,
                    user_id=demo_user.id
                ),
                Post(
                    title='Landscape Oil Painting',
                    description='Serene mountain landscape captured in oils. Available for commissioning.',
                    image_url='https://images.unsplash.com/photo-1561214115-6d2f1b0609fa?w=400&h=300&fit=crop',
                    price=250.00,
                    is_for_sale=True,
                    user_id=demo_user.id
                ),
                Post(
                    title='Graphic Design Portfolio',
                    description='Collection of modern graphic design work - logos, branding, and layouts.',
                    image_url='https://images.unsplash.com/photo-1561070791-2526d30994b5?w=400&h=300&fit=crop',
                    price=None,
                    is_for_sale=False,
                    user_id=demo_user.id
                ),
                Post(
                    title='Character Illustration',
                    description='Original character design with detailed costume and expression.',
                    image_url='https://images.unsplash.com/photo-1561214115-6d2f1b0609fa?w=400&h=300&fit=crop',
                    price=120.00,
                    is_for_sale=True,
                    user_id=demo_user.id
                ),
            ]
            for post in sample_posts:
                db.session.add(post)
            db.session.commit()

        return jsonify({'success': True, 'message': 'Demo data created'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    try:
        return render_template('error.html', error='Page not found'), 404
    except Exception:
        return ("<h1>404 - Page not found</h1>", 404)

@app.errorhandler(500)
def server_error(e):
    try:
        return render_template('error.html', error='Server error'), 500
    except Exception:
        return ("<h1>500 - Server error</h1>", 500)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)
