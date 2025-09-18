# Email OTP Troubleshooting Guide

## Quick Diagnosis

### 1. **Test Email Configuration**
Visit: `http://localhost:5000/test-email` to test your email setup

### 2. **Check Console Output**
Look for detailed error messages in your terminal/console when trying to send OTP.

## Common Issues & Solutions

### ❌ **Issue 1: "Email credentials not configured"**

**Error Message:**
```
ERROR: Email credentials not configured. Please set MAIL_USERNAME and MAIL_PASSWORD in .env file
```

**Solution:**
1. Create a `.env` file in your project root
2. Add these lines:
```env
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_DEFAULT_SENDER=noreply@uts2.com
```

### ❌ **Issue 2: Gmail Authentication Failed**

**Error Message:**
```
SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')
```

**Solution:**
1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate App Password:**
   - Go to Google Account Settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"
   - Use this 16-character password (not your regular password)

### ❌ **Issue 3: SMTP Connection Refused**

**Error Message:**
```
SMTPConnectError: (111, 'Connection refused')
```

**Solutions:**
1. **Check Firewall:** Ensure port 587 is not blocked
2. **Try Different Port:** Change `MAIL_PORT=465` and `MAIL_USE_TLS=False`
3. **Check Network:** Ensure internet connection is working

### ❌ **Issue 4: "Less secure app access" Error**

**Error Message:**
```
SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')
```

**Solution:**
1. Go to Google Account Settings
2. Security → Less secure app access
3. Turn ON "Allow less secure apps"
4. **Note:** This is less secure, prefer App Passwords

### ❌ **Issue 5: SSL/TLS Certificate Error**

**Error Message:**
```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Solution:**
Add this to your `.env` file:
```env
MAIL_USE_TLS=False
MAIL_USE_SSL=True
MAIL_PORT=465
```

## Alternative Email Providers

### **Outlook/Hotmail**
```env
MAIL_SERVER=smtp-mail.outlook.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@outlook.com
MAIL_PASSWORD=your-password
```

### **Yahoo Mail**
```env
MAIL_SERVER=smtp.mail.yahoo.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@yahoo.com
MAIL_PASSWORD=your-app-password
```

### **SendGrid (Recommended for Production)**
```env
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=apikey
MAIL_PASSWORD=your-sendgrid-api-key
```

## Testing Steps

### 1. **Check Configuration**
```bash
# Visit this URL in your browser
http://localhost:5000/test-email
```

### 2. **Test with Console**
```python
# Add this to your app.py temporarily for testing
@app.route('/debug-email')
def debug_email():
    print("MAIL_SERVER:", app.config['MAIL_SERVER'])
    print("MAIL_PORT:", app.config['MAIL_PORT'])
    print("MAIL_USERNAME:", app.config['MAIL_USERNAME'])
    print("MAIL_PASSWORD:", "SET" if app.config['MAIL_PASSWORD'] else "NOT SET")
    return "Check console output"
```

### 3. **Manual SMTP Test**
```python
import smtplib
from email.mime.text import MIMEText

def test_smtp():
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('your-email@gmail.com', 'your-app-password')
        
        msg = MIMEText('Test email')
        msg['Subject'] = 'Test'
        msg['From'] = 'your-email@gmail.com'
        msg['To'] = 'test@example.com'
        
        server.send_message(msg)
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error: {e}")
```

## Production Recommendations

### 1. **Use Professional Email Service**
- **SendGrid** (Free tier: 100 emails/day)
- **AWS SES** (Very cheap, reliable)
- **Mailgun** (Developer-friendly)

### 2. **Environment Variables**
Never hardcode credentials in your code. Always use environment variables.

### 3. **Error Handling**
The current implementation includes comprehensive error logging. Check your console for detailed error messages.

## Quick Fix Checklist

- [ ] `.env` file exists in project root
- [ ] `MAIL_USERNAME` and `MAIL_PASSWORD` are set
- [ ] For Gmail: Using App Password (not regular password)
- [ ] 2-Factor Authentication enabled on Gmail
- [ ] Port 587 is not blocked by firewall
- [ ] Internet connection is working
- [ ] Flask-Mail is installed: `pip install Flask-Mail==0.9.1`

## Still Having Issues?

1. **Check the test endpoint:** `http://localhost:5000/test-email`
2. **Look at console output** for detailed error messages
3. **Try a different email provider** (Outlook, Yahoo)
4. **Use a professional email service** for production

The improved error logging will now show you exactly what's wrong with your email configuration!
