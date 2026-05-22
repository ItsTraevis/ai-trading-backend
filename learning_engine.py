# backend/learning_engine.py
learning_memory = {}

def update_learning_score(setup_id, won, profit_loss):
    learning_memory[setup_id] = {
        "won": won,
        "profit_loss": profit_loss,
        "lesson": "Setup performed well" if won else "Setup needs review"
    }

    return {
        "status": "learning_updated",
        "setup_id": setup_id,
        "memory": learning_memory[setup_id]
    }
