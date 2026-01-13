from fastmcp import FastMCP
import os
import aiosqlite
import tempfile
import json
from datetime import datetime, timedelta

# Setup paths
TEMP_DIR = tempfile.gettempdir()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("ExpenseTracker")

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Initialize the database synchronously"""
    try:
        import sqlite3
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT DEFAULT '',
                    note TEXT DEFAULT ''
                )
            """)
            # Test write access
            c.execute("INSERT OR IGNORE INTO expenses(date, amount, category) VALUES ('2000-01-01', 0, 'test')")
            c.execute("DELETE FROM expenses WHERE category = 'test'")
            print("Database initialized successfully with write access")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

init_db()

# ============================================================================
# TOOLS - Actions the AI can perform
# ============================================================================

@mcp.tool()
async def add_expense(date: str, amount: float, category: str, subcategory: str = "", note: str = ""):
    """
    Add a new expense entry to the database.
    
    Args:
        date: Date in YYYY-MM-DD format
        amount: Amount spent (positive number)
        category: Expense category (e.g., "Food & Dining", "Transportation")
        subcategory: Optional subcategory for more detail
        note: Optional note or description
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note)
            )
            expense_id = cur.lastrowid
            await c.commit()
            return {"status": "success", "id": expense_id, "message": "Expense added successfully"}
    except Exception as e:
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        return {"status": "error", "message": f"Database error: {str(e)}"}

@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    """
    List expense entries within an inclusive date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        List of expense records with id, date, amount, category, subcategory, and note
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date)
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": f"Error listing expenses: {str(e)}"}

@mcp.tool()
async def summarize_expenses(start_date: str, end_date: str, category: str = None):
    """
    Summarize expenses by category within an inclusive date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        category: Optional category to filter by
    
    Returns:
        Summary showing total amount and count per category
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            query = """
                SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cur = await c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": f"Error summarizing expenses: {str(e)}"}

@mcp.tool()
async def delete_expense(expense_id: int):
    """
    Delete an expense entry by ID.
    
    Args:
        expense_id: The ID of the expense to delete
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            await c.commit()
            if cur.rowcount > 0:
                return {"status": "success", "message": f"Expense {expense_id} deleted"}
            else:
                return {"status": "error", "message": f"Expense {expense_id} not found"}
    except Exception as e:
        return {"status": "error", "message": f"Error deleting expense: {str(e)}"}

@mcp.tool()
async def update_expense(expense_id: int, date: str = None, amount: float = None, 
                        category: str = None, subcategory: str = None, note: str = None):
    """
    Update an existing expense entry. Only provided fields will be updated.
    
    Args:
        expense_id: The ID of the expense to update
        date: New date in YYYY-MM-DD format (optional)
        amount: New amount (optional)
        category: New category (optional)
        subcategory: New subcategory (optional)
        note: New note (optional)
    """
    try:
        # Build dynamic update query
        updates = []
        params = []
        
        if date is not None:
            updates.append("date = ?")
            params.append(date)
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if subcategory is not None:
            updates.append("subcategory = ?")
            params.append(subcategory)
        if note is not None:
            updates.append("note = ?")
            params.append(note)
        
        if not updates:
            return {"status": "error", "message": "No fields to update"}
        
        params.append(expense_id)
        query = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?"
        
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(query, params)
            await c.commit()
            if cur.rowcount > 0:
                return {"status": "success", "message": f"Expense {expense_id} updated"}
            else:
                return {"status": "error", "message": f"Expense {expense_id} not found"}
    except Exception as e:
        return {"status": "error", "message": f"Error updating expense: {str(e)}"}

# ============================================================================
# PROMPTS - Pre-defined prompt templates for common tasks
# ============================================================================

@mcp.prompt()
def monthly_report(month: str = None, year: str = None):
    """
    Generate a comprehensive monthly expense report.
    
    Args:
        month: Month number (1-12), defaults to current month
        year: Year (YYYY), defaults to current year
    """
    if not month or not year:
        now = datetime.now()
        month = month or str(now.month)
        year = year or str(now.year)
    
    # Calculate date range
    start_date = f"{year}-{month.zfill(2)}-01"
    # Get last day of month
    if int(month) == 12:
        end_date = f"{year}-{month.zfill(2)}-31"
    else:
        next_month = datetime(int(year), int(month) + 1, 1)
        last_day = (next_month - timedelta(days=1)).day
        end_date = f"{year}-{month.zfill(2)}-{last_day}"
    
    return f"""Please generate a comprehensive expense report for {month}/{year}.

1. First, list all expenses from {start_date} to {end_date}
2. Then, summarize the expenses by category
3. Calculate the total spending for the month
4. Identify the top 3 spending categories
5. Provide insights on spending patterns and recommendations for the next month

Make the report clear, formatted, and easy to understand."""

@mcp.prompt()
def budget_analysis(budget: float, start_date: str = None, end_date: str = None):
    """
    Analyze spending against a budget.
    
    Args:
        budget: Total budget amount
        start_date: Start date (YYYY-MM-DD), defaults to current month start
        end_date: End date (YYYY-MM-DD), defaults to today
    """
    if not start_date or not end_date:
        now = datetime.now()
        start_date = start_date or f"{now.year}-{str(now.month).zfill(2)}-01"
        end_date = end_date or now.strftime("%Y-%m-%d")
    
    return f"""Analyze my spending against my budget of ${budget} for the period {start_date} to {end_date}.

1. Get all expenses for this period
2. Calculate total spending
3. Compare against the budget of ${budget}
4. Show spending by category
5. Calculate percentage of budget used
6. Identify if I'm on track or over budget
7. Provide specific recommendations to stay within or get back to budget

Present the analysis with clear numbers and actionable advice."""

@mcp.prompt()
def spending_trends(category: str = None, months: int = 3):
    """
    Analyze spending trends over time.
    
    Args:
        category: Optional category to analyze (analyzes all if not specified)
        months: Number of months to analyze (default 3)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)
    
    category_text = f" for the '{category}' category" if category else " across all categories"
    
    return f"""Analyze my spending trends{category_text} over the past {months} months.

1. Get expenses from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
2. Break down spending by month
3. Calculate month-over-month changes
4. Identify spending patterns (increasing, decreasing, stable)
5. Highlight any unusual spikes or drops
6. Provide insights on trends and recommendations

Present with clear month-by-month comparison."""

@mcp.prompt()
def quick_add(description: str):
    """
    Quick add an expense from natural language description.
    
    Args:
        description: Natural language description (e.g., "coffee $5.50 this morning")
    """
    return f"""Add an expense based on this description: "{description}"

Please:
1. Extract the amount, category, and any other relevant details
2. Use today's date unless a different date is mentioned
3. Choose the most appropriate category from available categories
4. Add the expense
5. Confirm what was added with a summary

If anything is unclear, ask for clarification before adding."""

# ============================================================================
# RESOURCES - Static or dynamic data the AI can access
# ============================================================================

@mcp.resource("expense:///categories")
def get_categories():
    """
    Get the list of available expense categories.
    Returns JSON with all valid categories and their subcategories.
    """
    default_categories = {
        "categories": [
            {
                "name": "Food & Dining",
                "subcategories": ["Groceries", "Restaurants", "Coffee & Snacks", "Delivery"]
            },
            {
                "name": "Transportation",
                "subcategories": ["Gas", "Public Transit", "Parking", "Car Maintenance", "Rideshare"]
            },
            {
                "name": "Shopping",
                "subcategories": ["Clothing", "Electronics", "Home Goods", "Personal Care"]
            },
            {
                "name": "Entertainment",
                "subcategories": ["Movies", "Games", "Sports", "Hobbies", "Subscriptions"]
            },
            {
                "name": "Bills & Utilities",
                "subcategories": ["Rent/Mortgage", "Electric", "Water", "Internet", "Phone", "Insurance"]
            },
            {
                "name": "Healthcare",
                "subcategories": ["Doctor", "Dentist", "Pharmacy", "Gym", "Therapy"]
            },
            {
                "name": "Travel",
                "subcategories": ["Flights", "Hotels", "Activities", "Souvenirs"]
            },
            {
                "name": "Education",
                "subcategories": ["Tuition", "Books", "Courses", "Supplies"]
            },
            {
                "name": "Business",
                "subcategories": ["Office Supplies", "Software", "Equipment", "Services"]
            },
            {
                "name": "Other",
                "subcategories": ["Gifts", "Donations", "Miscellaneous"]
            }
        ]
    }
    
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return json.dumps(default_categories, indent=2)

@mcp.resource("expense:///stats")
async def get_statistics():
    """
    Get overall expense statistics.
    Returns JSON with total expenses, counts, date ranges, etc.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            # Total expenses
            cur = await c.execute("SELECT COUNT(*), SUM(amount) FROM expenses")
            row = await cur.fetchone()
            total_count = row[0] or 0
            total_amount = row[1] or 0.0
            
            # Date range
            cur = await c.execute("SELECT MIN(date), MAX(date) FROM expenses")
            row = await cur.fetchone()
            min_date = row[0]
            max_date = row[1]
            
            # Category breakdown
            cur = await c.execute("""
                SELECT category, COUNT(*), SUM(amount)
                FROM expenses
                GROUP BY category
                ORDER BY SUM(amount) DESC
            """)
            categories = []
            async for row in cur:
                categories.append({
                    "category": row[0],
                    "count": row[1],
                    "total": row[2]
                })
            
            stats = {
                "total_expenses": total_count,
                "total_amount": total_amount,
                "date_range": {
                    "first_expense": min_date,
                    "last_expense": max_date
                },
                "by_category": categories
            }
            
            return json.dumps(stats, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.resource("expense:///help")
def get_help():
    """
    Get help documentation for the expense tracker.
    Returns markdown-formatted help text.
    """
    help_text = """# Expense Tracker Help

## Available Tools

### add_expense
Add a new expense to the tracker.
- **date**: Date in YYYY-MM-DD format
- **amount**: Amount spent (positive number)
- **category**: One of the available categories
- **subcategory** (optional): Subcategory for more detail
- **note** (optional): Additional notes

### list_expenses
List expenses within a date range.
- **start_date**: Start date (YYYY-MM-DD)
- **end_date**: End date (YYYY-MM-DD)

### summarize_expenses
Get spending summary by category.
- **start_date**: Start date (YYYY-MM-DD)
- **end_date**: End date (YYYY-MM-DD)
- **category** (optional): Filter by specific category

### delete_expense
Delete an expense by ID.
- **expense_id**: The ID of the expense to delete

### update_expense
Update an existing expense.
- **expense_id**: The ID to update
- Other fields are optional

## Available Prompts

### monthly_report
Generate a comprehensive monthly expense report.

### budget_analysis
Analyze spending against a budget.

### spending_trends
Analyze spending patterns over time.

### quick_add
Add expense from natural language.

## Example Queries

- "Add a $45.50 expense for groceries today"
- "Show me all my expenses from January"
- "What did I spend on food last month?"
- "Generate a monthly report for December 2024"
- "Am I within my $2000 budget this month?"
- "Show spending trends for the past 3 months"
"""
    return help_text

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)