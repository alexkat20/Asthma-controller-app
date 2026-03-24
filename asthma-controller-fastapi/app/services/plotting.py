from typing import List
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os


def generate_correlation_plot(df: pd.DataFrame, user_id: int) -> str:
    df_encoded = pd.get_dummies(
        df, columns=["Extra info", "day_name", "Month", "Season"]
    )
    final_df = pd.concat([df, df_encoded], ignore_index=False)
    final_df = final_df.drop(
        columns=["Extra info", "day_name", "Month", "Season", "Date"]
    )
    corr_matrix = final_df.corr()["Maximum"].to_frame()

    plt.figure(figsize=(6, 10))
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f")
    plt.title("Correlation matrix")
    plot_path = f"correlation_plot_user_{user_id}.png"
    plt.savefig(plot_path)
    plt.close()

    return plot_path


def generate_peak_flow_plot(df: pd.DataFrame, user_id: int, period: str) -> str:
    plt.figure(figsize=(8, 4))
    plt.plot(df["Date"], df["Maximum"], marker="o")
    plt.title(f"Peak Flow Dynamics ({period})")
    plt.xlabel("Date")
    plt.ylabel("Peak Flow")
    plt.grid()
    plot_path = f"peak_flow_plot_user_{user_id}.png"
    plt.savefig(plot_path)
    plt.close()

    return plot_path
