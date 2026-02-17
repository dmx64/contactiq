#!/bin/bash

# ContactIQ Deployment Script
# Automated deployment to production server

set -e  # Exit on any error

# Configuration
REPO_URL="https://github.com/dmx64/contactiq.git"
BRANCH="main"
APP_NAME="contactiq"
BACKEND_PORT="5000"
FRONTEND_PORT="3000"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root for security reasons."
    fi
}

# Check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    # Check Python 3.8+
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is required but not installed."
    fi
    
    local python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [[ $(echo "$python_version < 3.8" | bc -l) -eq 1 ]]; then
        error "Python 3.8+ is required. Current version: $python_version"
    fi
    
    # Check Node.js 18+
    if ! command -v node &> /dev/null; then
        error "Node.js is required but not installed."
    fi
    
    local node_version=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
    if [[ $node_version -lt 18 ]]; then
        error "Node.js 18+ is required. Current version: v$node_version"
    fi
    
    # Check Git
    if ! command -v git &> /dev/null; then
        error "Git is required but not installed."
    fi
    
    # Check pm2 for process management
    if ! command -v pm2 &> /dev/null; then
        warn "PM2 not found. Installing globally..."
        npm install -g pm2
    fi
    
    log "✓ All requirements met"
}

# Clone or update repository
setup_repository() {
    log "Setting up repository..."
    
    if [[ -d "$APP_NAME" ]]; then
        info "Repository exists. Updating..."
        cd $APP_NAME
        git fetch origin
        git reset --hard origin/$BRANCH
        cd ..
    else
        info "Cloning repository..."
        git clone -b $BRANCH $REPO_URL $APP_NAME
    fi
    
    cd $APP_NAME
    log "✓ Repository ready"
}

# Setup Python backend
setup_backend() {
    log "Setting up Python backend..."
    
    cd backend
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "venv" ]]; then
        info "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install dependencies
    info "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Setup environment file
    if [[ ! -f ".env" ]]; then
        info "Creating environment configuration..."
        cp .env.example .env
        warn "Please edit backend/.env file with your configuration"
    fi
    
    # Initialize database
    info "Initializing database..."
    python3 server.py --init-db
    
    cd ..
    log "✓ Backend setup complete"
}

# Setup React Native mobile app (for development)
setup_mobile() {
    log "Setting up React Native mobile app..."
    
    cd mobile
    
    # Install dependencies
    info "Installing Node.js dependencies..."
    npm ci
    
    # Create development build
    info "Preparing development build..."
    npx expo prebuild --clear
    
    cd ..
    log "✓ Mobile app setup complete"
}

# Install system services
install_services() {
    log "Installing system services..."
    
    # Create systemd service for backend
    sudo tee /etc/systemd/system/contactiq-backend.service > /dev/null <<EOF
[Unit]
Description=ContactIQ Backend API
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=$USER
WorkingDirectory=$(pwd)/backend
Environment=PATH=/usr/bin:/usr/local/bin
Environment=FLASK_ENV=production
ExecStart=$(pwd)/backend/venv/bin/python server.py
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=contactiq-backend

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable services
    sudo systemctl daemon-reload
    sudo systemctl enable contactiq-backend
    
    log "✓ System services installed"
}

# Setup nginx reverse proxy
setup_nginx() {
    log "Setting up Nginx reverse proxy..."
    
    # Check if nginx is installed
    if ! command -v nginx &> /dev/null; then
        info "Installing Nginx..."
        sudo apt update
        sudo apt install -y nginx
    fi
    
    # Create nginx configuration
    sudo tee /etc/nginx/sites-available/contactiq > /dev/null <<EOF
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Backend API
    location /api/ {
        proxy_pass http://localhost:$BACKEND_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # CORS headers
        add_header Access-Control-Allow-Origin *;
        add_header Access-Control-Allow-Methods 'GET, POST, PUT, DELETE, OPTIONS';
        add_header Access-Control-Allow-Headers 'DNT,X-CustomHeader,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Authorization,X-API-Key';
        
        if (\$request_method = 'OPTIONS') {
            return 204;
        }
    }
    
    # Health check
    location /health {
        proxy_pass http://localhost:$BACKEND_PORT/health;
    }
    
    # Static files
    location / {
        root /var/www/contactiq;
        try_files \$uri \$uri/ =404;
        add_header Cache-Control "public, max-age=3600";
    }
}
EOF

    # Enable site
    sudo ln -sf /etc/nginx/sites-available/contactiq /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test nginx configuration
    sudo nginx -t
    
    # Restart nginx
    sudo systemctl restart nginx
    sudo systemctl enable nginx
    
    log "✓ Nginx configured"
}

# Setup SSL certificate with Let's Encrypt
setup_ssl() {
    log "Setting up SSL certificate..."
    
    # Install certbot
    if ! command -v certbot &> /dev/null; then
        info "Installing Certbot..."
        sudo apt install -y certbot python3-certbot-nginx
    fi
    
    warn "To complete SSL setup, run:"
    echo "sudo certbot --nginx -d your-domain.com -d www.your-domain.com"
    
    log "✓ SSL setup prepared"
}

# Setup monitoring and logging
setup_monitoring() {
    log "Setting up monitoring and logging..."
    
    # Create log directories
    sudo mkdir -p /var/log/contactiq
    sudo chown $USER:$USER /var/log/contactiq
    
    # Setup log rotation
    sudo tee /etc/logrotate.d/contactiq > /dev/null <<EOF
/var/log/contactiq/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    create 0644 $USER $USER
}
EOF

    # Install monitoring tools
    if ! command -v htop &> /dev/null; then
        sudo apt install -y htop
    fi
    
    log "✓ Monitoring setup complete"
}

# Setup firewall
setup_firewall() {
    log "Setting up firewall..."
    
    # Install ufw if not present
    if ! command -v ufw &> /dev/null; then
        sudo apt install -y ufw
    fi
    
    # Configure firewall rules
    sudo ufw --force reset
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow ssh
    sudo ufw allow 80
    sudo ufw allow 443
    sudo ufw --force enable
    
    log "✓ Firewall configured"
}

# Start services
start_services() {
    log "Starting services..."
    
    # Start backend service
    sudo systemctl start contactiq-backend
    
    # Check service status
    if sudo systemctl is-active --quiet contactiq-backend; then
        log "✓ Backend service started successfully"
    else
        error "Failed to start backend service"
    fi
    
    # Wait for service to be ready
    info "Waiting for backend to be ready..."
    for i in {1..30}; do
        if curl -f http://localhost:$BACKEND_PORT/health &> /dev/null; then
            log "✓ Backend is ready"
            break
        fi
        sleep 2
    done
}

# Health check
health_check() {
    log "Running health checks..."
    
    # Check backend API
    if curl -f http://localhost:$BACKEND_PORT/health &> /dev/null; then
        log "✓ Backend API is healthy"
    else
        error "Backend API health check failed"
    fi
    
    # Check nginx
    if sudo systemctl is-active --quiet nginx; then
        log "✓ Nginx is running"
    else
        error "Nginx is not running"
    fi
    
    # Check database
    cd backend
    source venv/bin/activate
    if python3 -c "import sqlite3; conn = sqlite3.connect('contactiq.db'); print('Database OK')"; then
        log "✓ Database is accessible"
    else
        error "Database check failed"
    fi
    cd ..
    
    log "✓ All health checks passed"
}

# Backup function
create_backup() {
    log "Creating backup..."
    
    local backup_dir="/var/backups/contactiq"
    local backup_file="contactiq-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    
    sudo mkdir -p $backup_dir
    
    tar -czf "/tmp/$backup_file" \
        --exclude="node_modules" \
        --exclude="venv" \
        --exclude="*.log" \
        .
    
    sudo mv "/tmp/$backup_file" "$backup_dir/"
    
    # Keep only last 5 backups
    sudo bash -c "cd $backup_dir && ls -t contactiq-backup-*.tar.gz | tail -n +6 | xargs rm -f"
    
    log "✓ Backup created: $backup_dir/$backup_file"
}

# Show deployment summary
show_summary() {
    echo ""
    echo "======================================="
    echo "🚀 ContactIQ Deployment Complete! 🚀"
    echo "======================================="
    echo ""
    echo "📱 Backend API: http://localhost:$BACKEND_PORT"
    echo "🌐 Nginx Proxy: http://your-domain.com"
    echo "📊 Service Status: sudo systemctl status contactiq-backend"
    echo "📝 Logs: journalctl -u contactiq-backend -f"
    echo ""
    echo "🔧 Next Steps:"
    echo "1. Edit backend/.env with your configuration"
    echo "2. Configure domain in nginx settings"
    echo "3. Setup SSL: sudo certbot --nginx -d your-domain.com"
    echo "4. Test mobile app: cd mobile && npm start"
    echo ""
    echo "📚 Documentation:"
    echo "- API Docs: docs/API.md"
    echo "- Deployment Guide: docs/DEPLOYMENT.md"
    echo ""
    echo "✨ Happy Intelligence Gathering! ✨"
}

# Main deployment function
main() {
    log "Starting ContactIQ deployment..."
    
    check_root
    check_requirements
    setup_repository
    setup_backend
    setup_mobile
    install_services
    setup_nginx
    setup_ssl
    setup_monitoring
    setup_firewall
    create_backup
    start_services
    health_check
    show_summary
    
    log "🎉 Deployment completed successfully!"
}

# Run deployment
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
