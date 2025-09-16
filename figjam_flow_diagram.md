# UTS Database Dashboard - FigJam Flow Diagram

## FigJam-Ready Flow Chart

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           UTS DATABASE DASHBOARD PLATFORM                      │
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
│                                                                                 │
│  ┌─────────────────┐                    ┌─────────────────┐                    │
│  │   LOGIN PAGE    │                    │ REGISTER PAGE   │                    │
│  │                 │                    │                 │                    │
│  │ • Username/Email│                    │ • Full Name     │                    │
│  │ • Password      │                    │ • Username      │                    │
│  │ • Remember Me   │                    │ • Email         │                    │
│  │ • Forgot Pass   │                    │ • Password      │                    │
│  └─────────────────┘                    │ • Confirm Pass  │                    │
│           │                             └─────────────────┘                    │
│           │                                       │                            │
│           ▼                                       ▼                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        USER MANAGER                                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │   Password  │  │   Session   │  │   User      │  │   Avatar    │   │   │
│  │  │   Hashing   │  │ Management  │  │   Storage   │  │ Management  │   │   │
│  │  │ (PBKDF2)    │  │ (30 days)   │  │ (JSON)      │  │ (Upload)    │   │   │
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
- Login/Register pages
- User Manager
- Session Management
- Profile Management

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

## 🆕 **Additional Components to Add:**

### **🔵 BLUE - Security & Permissions**
- Role-based access control (Admin/User)
- Password reset functionality
- Session timeout handling
- Security audit logging

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
