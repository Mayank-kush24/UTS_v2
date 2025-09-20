# Jarvis Database Dashboard - FigJam Flow Diagram

## FigJam-Ready Flow Chart

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           JARVIS DATABASE DASHBOARD PLATFORM                   │
│                              (Flask Web Application)                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER ENTRY POINT                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   Browser   │    │  Mobile     │    │   Desktop   │    │   Tablet    │     │
│  │   Access    │    │   Access    │    │   Access    │    │   Access    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            AUTHENTICATION LAYER                                │
│                                                                                │
│  ┌─────────────────┐                    ┌─────────────────┐                    │
│  │   MAIN LOGIN    │                    │ REGISTER PAGE   │                    │
│  │   (OTP PRIMARY) │                    │                 │                    │
│  │                 │                    │ • Full Name     │                    │
│  │ • Email Input   │                    │ • Username      │                    │
│  │ • Send OTP      │                    │ • Email         │                    │
│  │ • Toggle Pass   │                    │ • Password      │                    │
│  │ • Password Form │                    │ • Confirm Pass  │                    │
│  │   (Hidden)      │                    │                 │                    │
│  └─────────────────┘                    └─────────────────┘                    │
│           │                                       │                            │
│           ▼                                       ▼                            │
│  ┌─────────────────┐                    ┌─────────────────┐                    │
│  │   OTP LOGIN     │                    │ PASSWORD LOGIN  │                    │
│  │   (DEDICATED)   │                    │   (DEDICATED)   │                    │
│  │                 │                    │                 │                    │
│  │ • Email Input   │                    │ • Username      │                    │
│  │ • Send Code     │                    │ • Password      │                    │
│  │ • Resend OTP    │                    │ • Remember Me   │                    │
│  │ • Rate Limiting │                    │ • Forgot Pass   │                    │
│  └─────────────────┘                    └─────────────────┘                    │
│           │                                       │                            │
│           ▼                                       ▼                            │
│  ┌─────────────────┐                    ┌─────────────────┐                    │
│  │  OTP VERIFY     │                    │                 │                    │
│  │                 │                    │                 │                    │
│  │ • 6-Digit Code  │                    │                 │                    │
│  │ • Auto-Submit   │                    │                 │                    │
│  │ • Resend Timer  │                    │                 │                    │
│  │ • 5 Min Expiry  │                    │                 │                    │
│  └─────────────────┘                    │                 │                    │
│           │                             │                 │                    │
│           ▼                             ▼                 ▼                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        USER MANAGER                                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   Password  │  │   Session   │  │   User      │  │   Avatar    │   │   │
│  │  │   Hashing   │  │ Management  │  │   Storage   │  │ Management  │   │   │
│  │  │ (PBKDF2)    │  │ (30 days)   │  │ (JSON)      │  │ (Upload)    │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  │                                                                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   OTP       │  │   Email     │  │   Rate      │  │   Security  │   │   │
│  │  │   System    │  │   Sending   │  │   Limiting  │  │   Features  │   │   │
│  │  │ (6-digit)   │  │ (Flask-Mail)│  │ (3/hour)    │  │ (5min exp)  │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MAIN DASHBOARD                                    │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  CONNECTION     │  │  DATABASE       │  │  DATA           │  │  SYSTEM     │ │
│  │  STATUS CARD    │  │  INFO CARD      │  │  STATS CARD     │  │  CONFIG     │ │
│  │                 │  │                 │  │                 │  │  CARD       │ │
│  │ • Connected     │  │ • Database Name │  │ • Total Tables  │  │ • Settings  │ │
│  │ • Disconnected  │  │ • Host/Port     │  │ • Total Rows    │  │ • Users     │ │
│  │ • Last Checked  │  │ • User/DB       │  │ • Database Size │  │ • Security  │ │
│  │ • Test Button   │  │ • Last Connected│  │ • Performance   │  │ • Backup    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          QUICK ACTIONS                                │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   Manage    │  │   Create    │  │   System    │  │   Refresh   │   │   │
│  │  │  Databases  │  │Visualizations│  │  Settings   │  │    All     │   │   │
│  │  │             │  │             │  │             │  │   Data      │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            DATABASE MANAGEMENT                                 │
│                                                                                 │
│  ┌─────────────────┐                    ┌─────────────────┐                    │
│  │   ADD DATABASE  │                    │  EDIT DATABASE  │                    │
│  │                 │                    │                 │                    │
│  │ • Database Name │                    │ • Update Config │                    │
│  │ • Host/Port     │                    │ • Test Connection│                   │
│  │ • Username      │                    │ • Save Changes  │                    │
│  │ • Password      │                    │ • Delete Option │                    │
│  │ • Test Connect  │                    │                 │                    │
│  └─────────────────┘                    └─────────────────┘                    │
│           │                                       │                            │
│           ▼                                       ▼                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        DATABASE STORAGE                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   Database  │  │ Connection  │  │   Last      │  │   Status    │   │   │
│  │  │   Configs   │  │   Manager   │  │ Connected   │  │  Tracking   │   │   │
│  │  │   (JSON)    │  │ (PostgreSQL)│  │ Timestamp   │  │             │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            DATA VISUALIZATION                                  │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │   TABLE         │  │   CHART         │  │   GEOGRAPHIC    │  │   CUSTOM    │ │
│  │   ANALYSIS      │  │   GENERATION    │  │   VISUALIZATION │  │   QUERIES   │ │
│  │                 │  │                 │  │                 │  │             │ │
│  │ • Auto Discovery│  │ • Bar Charts    │  │ • Map Views     │  │ • SQL Editor│ │
│  │ • Column Types  │  │ • Line Charts   │  │ • Location Data │  │ • Query Exec│ │
│  │ • Data Samples  │  │ • Pie Charts    │  │ • Heat Maps     │  │ • Results   │ │
│  │ • Statistics    │  │ • Doughnut      │  │ • Interactive   │  │ • Export    │ │
│  │ • Relationships │  │ • Scatter Plots │  │ • Zoom/Pan      │  │ • Save      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        DATA PROCESSING                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   Data      │  │   Chart.js  │  │   Export    │  │   Real-time │   │   │
│  │  │ Retrieval   │  │ Rendering   │  │ Functions   │  │   Updates   │   │   │
│  │  │ (SQL)       │  │ (Frontend)  │  │ (CSV/JSON)  │  │ (AJAX)      │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                         │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │   CONNECTION    │  │   TABLE         │  │   VISUALIZATION │  │   USER      │ │
│  │   ENDPOINTS     │  │   ENDPOINTS     │  │   ENDPOINTS     │  │   ENDPOINTS │ │
│  │                 │  │                 │  │                 │  │             │ │
│  │ • /api/status   │  │ • /api/tables   │  │ • /api/viz/     │  │ • /api/users│ │
│  │ • /api/connect  │  │ • /api/table/   │  │   dashboard     │  │ • /api/     │ │
│  │ • /api/disconnect│ │ • /api/export   │  │ • /api/viz/     │  │   profile   │ │
│  │ • /api/test     │  │ • /api/columns  │  │   analysis      │  │ • /api/     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │   avatar    │ │
│                                                                 │             │ │
│  ┌─────────────────────────────────────────────────────────────┘             │ │
│  │                        JSON RESPONSES                                    │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   Success   │  │   Error     │  │   Data      │  │   Status    │   │   │
│  │  │   Messages  │  │   Handling  │  │   Objects   │  │   Codes     │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CONTROL PANEL                                     │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │   SERVER        │  │   PROCESS       │  │   BROWSER       │  │   SYSTEM    │ │
│  │   MANAGEMENT    │  │   MONITORING    │  │   INTEGRATION   │  │   MONITORING│ │
│  │                 │  │                 │  │                 │  │             │ │
│  │ • Start Server  │  │ • Live Logs     │  │ • Auto Launch  │  │ • CPU Usage │ │
│  │ • Stop Server   │  │ • Error Tracking│  │ • URL Opening  │  │ • Memory    │ │
│  │ • Restart       │  │ • Performance   │  │ • Status Check │  │ • Disk Space│ │
│  │ • Status Check  │  │ • PID Tracking  │  │ • Refresh      │  │ • Network   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘

## Color Coding for FigJam:

### 🔵 BLUE - Authentication & User Management
- Main Login (OTP Primary)
- OTP Login (Dedicated)
- Password Login (Dedicated)
- OTP Verification
- Register pages
- User Manager
- Session Management
- Profile Management
- OTP System
- Email Sending (Flask-Mail)
- Rate Limiting
- Security Features

### 🟢 GREEN - Database Operations
- Database Management
- Connection Management
- Data Storage
- PostgreSQL Integration

### 🟡 YELLOW - Data Visualization
- Chart Generation
- Table Analysis
- Geographic Visualization
- Custom Queries

### 🟠 ORANGE - System Configuration
- Settings Management
- View Configuration
- System Monitoring
- Control Panel

### 🔴 RED - API & Technical
- REST API Endpoints
- JSON Responses
- Error Handling
- Technical Components

## FigJam Setup Instructions:

1. **Create a new FigJam file**
2. **Use the color coding above** for different sections
3. **Copy each box** as a separate frame in FigJam
4. **Add arrows** between connected components
5. **Use sticky notes** for additional details
6. **Group related components** using FigJam's grouping feature
7. **Add icons** from FigJam's icon library for visual appeal

## Key Connections to Draw:

- User Entry → Authentication Layer
- Authentication → Main Dashboard
- Dashboard → Database Management
- Dashboard → Data Visualization
- Database Management → API Layer
- Data Visualization → API Layer
- API Layer → Control Panel
- All components → User Profile Management

## 🔐 **OTP Authentication Flow (NEW):**

### **Primary Flow:**
1. **User Entry** → **Main Login (OTP Primary)**
2. **Email Input** → **OTP Generation & Sending**
3. **OTP Verification** → **User Authentication**
4. **Authentication Success** → **Main Dashboard**

### **Secondary Flow:**
1. **User Entry** → **Main Login (OTP Primary)**
2. **Toggle Button** → **Password Login (Hidden)**
3. **Password Form** → **User Authentication**
4. **Authentication Success** → **Main Dashboard**

### **Dedicated Routes:**
- `/login` - Main login (OTP primary, password secondary)
- `/login-otp` - OTP-only login page
- `/login-password` - Password-only login page
- `/verify-otp` - OTP verification page
- `/resend-otp` - Resend OTP endpoint

### **Security Features:**
- **Rate Limiting**: Max 3 OTP requests per hour per email
- **Time Expiry**: OTP codes expire after 5 minutes
- **Attempt Limiting**: Max 3 verification attempts per OTP
- **Email Validation**: Proper email format checking
- **Auto-cleanup**: Expired OTPs are automatically removed

## 🆕 **Additional Components to Add:**

### **🔵 BLUE - Security & Permissions**
- Role-based access control (Admin/User)
- Password reset functionality
- Session timeout handling
- Security audit logging
- OTP-based authentication
- Email verification system
- Rate limiting and security controls

### **🎨 UI/UX Enhancements (NEW)**
- Toggle functionality for login methods
- Smooth animations and transitions
- Responsive design for all devices
- Auto-focus management
- Loading states and visual feedback
- Clean, modern interface design
- Progressive disclosure of options

### **🟢 GREEN - Data Management**
- Data export/import functionality
- Backup and restore operations
- Data validation and cleaning
- Performance optimization

### **🟡 YELLOW - Advanced Analytics**
- Real-time data streaming
- Predictive analytics
- Machine learning integration
- Custom dashboard creation

### **🟠 ORANGE - System Operations**
- Logging and monitoring
- Error tracking and reporting
- Performance metrics
- Health checks

### **🔴 RED - Integration Layer**
- Third-party API integrations
- Webhook support
- Plugin architecture
- External data sources

## 📋 **Implementation Status Checklist:**

### **✅ Completed Features:**
- [x] User authentication and management
- [x] **OTP-based login system (Primary)**
- [x] **Email OTP verification**
- [x] **Password login (Secondary)**
- [x] **Toggle functionality for login methods**
- [x] **Rate limiting for OTP requests**
- [x] **Email sending with Flask-Mail**
- [x] **Smooth animations and transitions**
- [x] Database connection management
- [x] Basic data visualization
- [x] Geographic mapping
- [x] Custom chart creation
- [x] Filter system
- [x] REST API endpoints
- [x] Responsive UI design

### **🔄 In Progress:**
- [ ] Advanced user roles and permissions
- [ ] Data export functionality
- [ ] Real-time updates
- [ ] Performance monitoring

### **📋 Planned Features:**
- [ ] Machine learning integration
- [ ] Advanced analytics
- [ ] Plugin system
- [ ] Mobile app
- [ ] API documentation
- [ ] Automated testing

This structure will give you a comprehensive, FigJam-ready flow diagram that you can easily replicate and customize!

## 🚀 **Recent Updates (OTP Authentication System):**

### **Key Changes Made:**
1. **Primary OTP Login**: Main login page now shows OTP form by default
2. **Hidden Password Form**: Password login is hidden and only shows on toggle
3. **Smooth Animations**: Toggle functionality with slide and fade effects
4. **Smart Focus Management**: Auto-focuses appropriate fields
5. **Enhanced Security**: Rate limiting, time expiry, and attempt limiting
6. **Email Integration**: Flask-Mail for sending OTP codes
7. **Responsive Design**: Works perfectly on all devices

### **New Routes Added:**
- `/login` - Main login (OTP primary, password secondary)
- `/login-otp` - Dedicated OTP login page
- `/login-password` - Dedicated password login page
- `/verify-otp` - OTP verification page
- `/resend-otp` - Resend OTP endpoint

### **Technical Improvements:**
- **Smart Form Detection**: Single route handles both OTP and password
- **JavaScript Enhancements**: Dual form support with proper validation
- **CSS Animations**: Smooth transitions and visual feedback
- **Security Features**: Comprehensive rate limiting and validation
- **User Experience**: Clean, focused interface with progressive disclosure

### **Benefits:**
- **More Secure**: OTP is more secure than passwords
- **User Friendly**: No need to remember passwords
- **Mobile Optimized**: OTP works great on mobile devices
- **Flexible**: Both methods available with easy toggle
- **Modern**: Clean, professional interface with smooth animations
