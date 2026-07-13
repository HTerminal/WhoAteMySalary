# -*- coding: utf-8 -*-
"""Category list + auto-guess. A broad, India-friendly set based on common
personal-finance apps; users can also add their own (config['custom_categories'])."""

# Spending / expense categories (money OUT)
EXPENSE_CATEGORIES = [
    # everyday
    "Groceries",
    "Food & dining",
    "Food delivery",
    "Shopping & retail",
    "Fashion & clothing",
    "Electronics & gadgets",
    "Household & essentials",
    # home & bills
    "Rent & housing",
    "Utilities (electricity/water/gas)",
    "Internet & mobile",
    "Insurance",
    "Subscriptions & digital",
    # getting around
    "Travel & transport",
    "Taxi & ride-hailing",
    "Fuel",
    # health & self
    "Medical & healthcare",
    "Pharmacy & wellness",
    "Personal care & grooming",
    "Fitness & sports",
    # life
    "Entertainment & leisure",
    "Education & learning",
    "Kids & family",
    "Pets",
    "Gifts & donations",
    # money movement
    "Credit Card bill payment",
    "Home Loan EMI - LIC Housing",
    "Loans & EMIs",
    "Investment / SIP",
    "Taxes & government",
    "Business / software services",
    "Bank charges & fees",
    "Cash withdrawal (ATM)",
    "Large outward transfer",
    "Self transfer (own a/c)",
    "Others / unknown (P2P)",
]

# Income categories (money IN)
INCOME_CATEGORIES = [
    "Salary",
    "Techshlok (business / salary)",
    "Business income",
    "Freelance / consulting",
    "Bank interest",
    "Investment / redemption",
    "Dividends & returns",
    "Rental income",
    "Refund / reversal",
    "Cashback & rewards",
    "Family / individual",
    "Gifts received",
    "Other incoming",
]

ALL_CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES

# Paying off a credit-card bill. This is NOT income, and it must NOT be counted as
# spending either — the individual card purchases are already counted, so counting
# the bill payment too would double-count. It gets its own bucket, excluded from
# both money-in and money-out totals.
CC_BILL_CATEGORY = "Credit Card bill payment"
CC_BILL_CATEGORIES = {CC_BILL_CATEGORY, "Credit Card bills (CRED)"}   # 2nd = legacy name


def is_cc_bill_payment(text):
    """True if the email is a credit-card *bill payment* (e.g. 'Payment received on
    your ICICI Bank Credit Card', or a CRED-app payment) — not a purchase."""
    d = (text or "").upper()
    # CRED app pays your card bill
    if "CRED" in d and ("CLUB" in d or "AXISB" in d or "CRED " in d or d.strip() == "CRED"):
        return True
    # "Payment received/credited on your credit card" (requires PAYMENT to avoid
    # matching purchase alerts, which say 'spent'/'used for a transaction')
    if "CREDIT CARD" in d and "PAYMENT" in d and any(k in d for k in ("RECEIVED", "CREDITED", "THANK YOU")):
        return True
    return False


def guess_category(text, direction):
    """text = merchant + subject + snippet; direction = 'IN' or 'OUT'."""
    d = (text or "").upper()

    if is_cc_bill_payment(text):
        return CC_BILL_CATEGORY

    if direction == "IN":
        if "TECHSHLO" in d:
            return "Techshlok (business / salary)"
        if any(k in d for k in ["SALARY", "SAL CREDIT", "PAYROLL", "STIPEND"]):
            return "Salary"
        if any(k in d for k in ["INT.PD", "SBINT", "INTEREST", "INT PD"]):
            return "Bank interest"
        if any(k in d for k in ["REFUND", "REVERSAL", "REVERSED", "IRCTC", "F06"]):
            return "Refund / reversal"
        if any(k in d for k in ["CASHBACK", "REWARD"]):
            return "Cashback & rewards"
        if "DIVIDEND" in d:
            return "Dividends & returns"
        if any(k in d for k in ["MUTUAL", "MOTILAL", "GROWW", "REDEMPTION", "ZERODHA",
                                "MATURITY"]):
            return "Investment / redemption"
        if "RENT" in d:
            return "Rental income"
        return "Other incoming"

    # ---- OUT ----
    if any(k in d for k in ["LICHOUSING", "LIC HOUSING", "WWW LICH"]):
        return "Home Loan EMI - LIC Housing"
    if any(k in d for k in ["BIGBASKET", "JIOMART", "DMART", "D MART", "RELIANCE FRESH",
                            "BLINKIT", "BLINK COMMERCE", "ZEPTO", "INSTAMART", "GROFERS",
                            "GROCERY", "KIRANA", "SUPERMARKET", "SUPER MARKET",
                            "MORE RETAIL", "SPENCER", "STAR BAZAAR"]):
        return "Groceries"
    if any(k in d for k in ["SWIGGY", "ZOMATO", "FOODPANDA", "UBEREATS", "UBER EATS",
                            "FAASOS", "EATSURE", "BOX8", "FRESHMENU", "FUDR"]):
        return "Food delivery"
    if any(k in d for k in ["NETFLIX", "SPOTIFY", "APPLE", "ADOBE", "GODADDY", "YOUTUBE",
                            "PRIME VIDEO", "HOTSTAR", "DISNEY", "SONYLIV", "ZEE5",
                            "GAANA", "AUDIBLE", "ICLOUD", "GOOGLE ONE"]):
        return "Subscriptions & digital"
    if any(k in d for k in ["JIO", "AIRTEL", "VODAFONE", " VI ", "BSNL", "RECHARGE",
                            "BROADBAND", "ACT FIBERNET", "HATHWAY", "TATASKY", "TATA SKY",
                            "DISH TV", "D2H", "DTH"]):
        return "Internet & mobile"
    if any(k in d for k in ["ELECTRICITY", "BESCOM", "TATA POWER", "ADANI ELEC", "MSEB",
                            "BILLDESK", "WATER BILL", "GAS BILL", "INDANE", "BHARATGAS",
                            "BHARAT GAS", "HP GAS", "LPG"]):
        return "Utilities (electricity/water/gas)"
    if any(k in d for k in ["UBER", "OLA", "OLACABS", "RAPIDO", "MERU", "BLABLACAR"]):
        return "Taxi & ride-hailing"
    if any(k in d for k in ["IRCTC", "RAILWAY", "INDIAN R", "DMRC", "METRO", "REDBUS",
                            "ABHIBUS", "FLIGHT", "INDIGO", "SPICEJET", "AIR INDIA",
                            "VISTARA", "MAKEMYTRIP", "GOIBIBO", "YATRA", "EASEMYTRIP",
                            "CLEARTRIP", "OYO", "AIRBNB"]):
        return "Travel & transport"
    if any(k in d for k in ["INDIANOIL", "INDIAN OIL", "HP PETROL", "BHARAT PET",
                            "PETROL", "FUEL", "IOCL", "BPCL", "HPCL", "SHELL", "NAYARA"]):
        return "Fuel"
    if any(k in d for k in ["APOLLO PHARM", "PHARMEASY", "NETMEDS", "1MG", "TATA 1MG",
                            "MEDPLUS", "WELLNESS FOREVER", "PHARMACY", "CHEMIST"]):
        return "Pharmacy & wellness"
    if any(k in d for k in ["HOSPITAL", "CLINIC", "MEDIC", "APOLLO", "FORTIS", "MANIPAL",
                            "ULTRASO", "THE KNEE", "GHIYA", "GLOBAL H", "GANESHAM",
                            "DIAGNOSTIC", "PATHOLOGY", "DOCTOR"]):
        return "Medical & healthcare"
    if any(k in d for k in ["POLICYBAZAAR", "INSURANCE", "HDFC LIFE", "ICICI PRU",
                            "SBI LIFE", "MAX LIFE", "TATA AIA", "STAR HEALTH", "ACKO",
                            "GO DIGIT", "PREMIUM PAID"]):
        return "Insurance"
    if any(k in d for k in ["CROMA", "RELIANCE DIGITAL", "VIJAY SALES"]):
        return "Electronics & gadgets"
    if any(k in d for k in ["MYNTRA", "AJIO", "ZARA", "H&M", "MAX FASHION", "LIFESTYLE",
                            "PANTALOON", "WESTSIDE", "SHOPPERS STOP", "NIKE", "ADIDAS",
                            "PUMA", "FASHION"]):
        return "Fashion & clothing"
    if any(k in d for k in ["RESTAURANT", "CAFE", "COFFEE", "BAKERY", "CAKE", "PIZZA",
                            "DOMINO", "MCDONALD", "KFC", "BURGER", "STARBUCKS", "BARBEQUE",
                            "DHABA", "FOOD", "KHANA", "GERMAN C", "BOMBAY M", "HALDIRAM",
                            "BIKANER", "SAVEUR", "BAKER"]):
        return "Food & dining"
    if any(k in d for k in ["FLIPKART", "AMAZON", "MEESHO", "SNAPDEAL", "TATA CLIQ",
                            "STORE", "MART", "RETAIL", "SHOP", "SOFA"]):
        return "Shopping & retail"
    if any(k in d for k in ["BYJU", "UNACADEMY", "UDEMY", "COURSERA", "VEDANTU",
                            "WHITEHAT", "SCHOOL", "COLLEGE", "UNIVERSITY", "TUITION",
                            "COACHING", "EXAM FEE", "ADMISSION"]):
        return "Education & learning"
    if any(k in d for k in ["BOOKMYSHOW", "PVR", "INOX", "CINEPOLIS", "CINEMA", "MOVIE",
                            "GAMING", "STEAM", "PLAYSTATION", "XBOX", "NINTENDO"]):
        return "Entertainment & leisure"
    if any(k in d for k in ["CULT.FIT", "CULTFIT", "GYM", "FITNESS", "DECATHLON"]):
        return "Fitness & sports"
    if any(k in d for k in ["NEWJAISA", "SOFT TEC", "AWS", "HOSTING", "DOMAIN", "SOFTWARE",
                            "DIGITALOCEAN", "AZURE", "GOOGLE CLOUD"]):
        return "Business / software services"
    if any(k in d for k in ["ATM WDR", "ATM ", "CASH WDL", "CASH WITHDRAW"]):
        return "Cash withdrawal (ATM)"
    if any(k in d for k in ["INCOME TAX", "GST PAY", "TDS", "ADVANCE TAX", "PROPERTY TAX",
                            "CHALLAN", "GOV.IN"]):
        return "Taxes & government"
    if any(k in d for k in ["CHRG", "CHARGE", "FEE", "GST", "SMS CHG", "MANDATE"]):
        return "Bank charges & fees"
    if any(k in d for k in ["EMI", "LOAN"]):
        return "Loans & EMIs"
    if any(k in d for k in ["IMPS", "NEFT", "RTGS"]):
        return "Large outward transfer"
    if "SIP" in d or "CLEARING CORP" in d:
        return "Investment / SIP"
    return "Others / unknown (P2P)"
