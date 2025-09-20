# Email OTP Login System

## Overview
The Jarvis application now includes a secure email OTP (One-Time Password) login system that allows users to authenticate without passwords.

## How It Works

### 1. **User Flow**
1. User visits `/login-otp` and enters their email address
2. System validates the email and checks if a user account exists
3. A 6-digit OTP is generated and sent to the user's email
4. User enters the OTP on the verification page
5. System verifies the OTP and logs the user in

### 2. **Security Features**
- **Time-limited OTPs**: Codes expire after 5 minutes
- **Rate limiting**: Maximum 3 OTP requests per email per hour
- **Attempt limiting**: Maximum 3 verification attempts per OTP
- **Auto-cleanup**: Expired OTPs are automatically removed
- **Secure generation**: OTPs use cryptographically secure random generation

### 3. **Email Configuration**
The system uses Flask-Mail to send OTP emails. Configure these environment variables:

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=noreply@jarvis.com
```

### 4. **Routes Added**
- `GET/POST /login-otp` - Email input page
- `GET/POST /verify-otp` - OTP verification page
- `POST /resend-otp` - Resend OTP (AJAX endpoint)

### 5. **Templates Added**
- `templates/auth/login_otp.html` - Email input form
- `templates/auth/verify_otp.html` - OTP verification form

### 6. **Features**
- **Responsive Design**: Works on all devices
- **Auto-submit**: Form submits automatically when 6 digits are entered
- **Resend Functionality**: Users can request a new OTP with cooldown
- **Visual Feedback**: Loading states, validation, and error messages
- **Accessibility**: Proper ARIA labels and keyboard navigation

## Setup Instructions

### 1. Install Dependencies
```bash
pip install Flask-Mail==0.9.1
```

### 2. Configure Email Settings
1. Copy settings from `email_config_example.txt` to your `.env` file
2. Update email configuration in `.env`
3. For Gmail, use an App Password instead of your regular password

### 3. Gmail Setup
1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password: Google Account → Security → App passwords
3. Use the App Password in `MAIL_PASSWORD`

### 4. Test the System
1. Start the application: `python app.py`
2. Visit `/login-otp`
3. Enter a valid email from your users.json
4. Check your email for the OTP
5. Enter the OTP to complete login

## Security Considerations

### 1. **Production Recommendations**
- Use Redis or database for OTP storage instead of in-memory
- Implement proper logging for security events
- Add IP-based rate limiting
- Use HTTPS in production
- Consider implementing CAPTCHA for additional protection

### 2. **Email Security**
- Use a dedicated email service (SendGrid, AWS SES, etc.)
- Implement SPF, DKIM, and DMARC records
- Monitor for suspicious activity

### 3. **OTP Security**
- OTPs are single-use and time-limited
- Failed attempts are tracked and limited
- No sensitive data is stored in OTPs

## Customization

### 1. **OTP Length**
Change the OTP length in `OTPSystem.generate_otp()`:
```python
def generate_otp(self, length=6):  # Change 6 to desired length
```

### 2. **Expiry Time**
Modify OTP expiry in `OTPSystem.__init__()`:
```python
self.otp_expiry = 300  # 5 minutes in seconds
```

### 3. **Rate Limiting**
Adjust rate limits in `OTPSystem.__init__()`:
```python
self.max_attempts = 3  # Max OTP requests per hour
self.rate_limit_window = 3600  # 1 hour in seconds
```

## Troubleshooting

### 1. **Email Not Sending**
- Check email configuration in `.env`
- Verify SMTP settings
- Check firewall/network restrictions
- Use Gmail App Password for Gmail

### 2. **OTP Not Working**
- Check if user exists in users.json
- Verify email address format
- Check rate limiting (max 3 attempts per hour)
- Ensure OTP hasn't expired (5 minutes)

### 3. **Template Issues**
- Ensure templates are in `templates/auth/` directory
- Check for JavaScript errors in browser console
- Verify Bootstrap CSS/JS is loaded

## Future Enhancements

1. **SMS OTP**: Add SMS-based OTP as alternative
2. **Push Notifications**: Mobile app notifications
3. **Biometric Login**: Fingerprint/face recognition
4. **Social Login**: Google/GitHub OAuth integration
5. **Advanced Security**: Device fingerprinting, location-based verification

## Files Modified/Created

### Modified Files:
- `app.py` - Added OTP system, routes, and email configuration
- `requirements.txt` - Added Flask-Mail dependency
- `templates/auth/login.html` - Added OTP login option

### New Files:
- `templates/auth/login_otp.html` - Email input page
- `templates/auth/verify_otp.html` - OTP verification page
- `email_config_example.txt` - Email configuration example
- `OTP_LOGIN_SYSTEM.md` - This documentation

## Usage

### For Users:
1. Go to the login page
2. Click "Login with Email Code"
3. Enter your email address
4. Check your email for the 6-digit code
5. Enter the code to complete login

### For Developers:
- The OTP system is fully integrated with the existing UserManager
- All existing authentication flows remain unchanged
- OTP login is an additional option, not a replacement
- Session management works the same way for both login methods
