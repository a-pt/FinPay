"""
FinPay Insights - Application Launcher.
Run with: python run.py
"""

from finpay import create_app

app = create_app()

if __name__ == "__main__":
    print("=======================================================")
    print("  🚀 FinPay Insights - Fintech Analytics Dashboard")
    print("  🌐 Server running at: http://127.0.0.1:5000")
    print("  👤 Demo Analyst: analyst@finpay.com / password123")
    print("  👤 Demo Admin:   admin@finpay.com / adminpassword")
    print("=======================================================")
    app.run(host="127.0.0.1", port=5000, debug=True)
