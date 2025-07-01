import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import pandas as pd
import sqlite3
from datetime import datetime
import os

class TradeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Trade Manager")
        self.root.geometry("1400x700")

        db_path = "trade_journal.db"
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.setup_database()

        self.data = pd.DataFrame()
        self.current_balance = 0.0
        self.date_sort_ascending = True

        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Левая панель (средний результат)
        self.stats_frame = tk.Frame(main_frame)
        self.stats_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.average_results = {
            "День": tk.StringVar(value="—"),
            "Неделя": tk.StringVar(value="—"),
            "Месяц": tk.StringVar(value="—"),
            "Квартал": tk.StringVar(value="—"),
            "Год": tk.StringVar(value="—")
        }

        tk.Label(self.stats_frame, text="Средний результат").pack(anchor="w")
        for period, var in self.average_results.items():
            tk.Label(self.stats_frame, text=f"{period}:").pack(anchor="w")
            tk.Label(self.stats_frame, textvariable=var, font=("Arial", 12, "bold")).pack(anchor="w")

        # Правая панель (кнопки)
        self.button_frame = tk.Frame(main_frame)
        self.button_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10)

        self.btn_load = tk.Button(self.button_frame, text="Загрузить Excel", command=self.load_excel)
        self.btn_load.pack(pady=5)

        self.btn_process = tk.Button(self.button_frame, text="Обработать сделки", command=self.process_trades)
        self.btn_process.pack(pady=5)

        self.btn_delete = tk.Button(self.button_frame, text="Удалить выбранную сделку", command=self.delete_selected_trade)
        self.btn_delete.pack(pady=5)

        self.btn_clear = tk.Button(self.button_frame, text="Очистить всю таблицу", command=self.clear_table)
        self.btn_clear.pack(pady=5)

        self.btn_add = tk.Button(self.button_frame, text="Добавить сделку вручную", command=self.add_manual_trade)
        self.btn_add.pack(pady=5)

        # Центральная панель (таблица)
        self.table_frame = tk.Frame(main_frame)
        self.table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ["Дата", "Тикер", "Открытие сделка", "Закрытие сделка", "Результат (%)", "Комментарии"]

        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings")

        self.tree.heading("Дата", text="Дата", command=self.sort_by_date)
        self.tree.heading("Тикер", text="Тикер")
        self.tree.heading("Открытие сделка", text="Открытие сделка")
        self.tree.heading("Закрытие сделка", text="Закрытие сделка")
        self.tree.heading("Результат (%)", text="Результат (%)")
        self.tree.heading("Комментарии", text="Комментарии")

        for col in columns:
            self.tree.column(col, width=180)

        # Добавляем скроллбары
        self.scrollbar_y = ttk.Scrollbar(self.table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=self.scrollbar_y.set)

        self.scrollbar_x = ttk.Scrollbar(self.table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.configure(xscrollcommand=self.scrollbar_x.set)

        self.tree.pack(fill=tk.BOTH, expand=True)

        # Настраиваем теги для зебрирования
        self.tree.tag_configure("odd", background="#f9f9f9")
        self.tree.tag_configure("even", background="#e6e6e6")

        self.tree.bind("<Double-1>", self.edit_comment)

        # При запуске загружаем имеющиеся сделки
        self.load_processed_data()
        self.calculate_average_results()

    def setup_database(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            ticker TEXT,
            open_lots REAL,
            open_price REAL,
            open_portfolio_percent REAL,
            close_lots REAL,
            close_price REAL,
            close_portfolio_percent REAL,
            result TEXT,
            operation_type TEXT,
            notes TEXT
        )
        """)
        self.conn.commit()

    def load_excel(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return
        try:
            raw_data = pd.read_excel(file_path)
            required_columns = ["Дата сделки", "Время сделки", "Название инструмента", "Операция", "Количество", "Цена"]
            for col in required_columns:
                if col not in raw_data.columns:
                    raise ValueError(f"Отсутствует колонка: {col}")

            raw_data["Дата сделки"] = pd.to_datetime(raw_data["Дата сделки"], format="%d.%m.%Y", errors="coerce")
            raw_data["Количество"] = (raw_data["Количество"].astype(str).str.replace(" ", "").str.replace(",", ".").astype(float))
            raw_data["Цена"] = (raw_data["Цена"].astype(str).str.replace(" ", "").str.replace(",", ".").astype(float))

            self.data = raw_data
            bal = simpledialog.askfloat("Баланс портфеля", "Введите текущий баланс портфеля:")
            if bal is None or bal <= 0:
                raise ValueError("Баланс портфеля должен быть больше 0.")
            self.current_balance = bal

            self.display_data()
            messagebox.showinfo("Успех", "Excel файл успешно загружен!")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить Excel файл: {e}")

    def display_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        if self.data.empty:
            return

        # Применяем зебрирование даже при отображении сырых данных
        for idx, (_, row) in enumerate(self.data.iterrows()):
            date_str = "-"
            if pd.notna(row["Дата сделки"]):
                date_str = row["Дата сделки"].strftime("%d.%m.%Y")
            ticker_val = row["Название инструмента"] if pd.notna(row["Название инструмента"]) else "-"
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(date_str, ticker_val, "-", "-", "-", "-"), tags=(tag,))

    def process_trades(self):
        if self.data.empty:
            messagebox.showwarning("Внимание", "Нет данных для обработки.")
            return
        if self.current_balance <= 0:
            messagebox.showwarning("Внимание", "Сначала введите корректный баланс портфеля.")
            return

        portfolio_balance = self.current_balance
        agg_df = self.aggregate_by_day()
        closed_trades = self.build_positions_and_close(agg_df, portfolio_balance)

        for t in closed_trades:
            result_str = self.format_result(t["price_change_percent"], t["portfolio_change_percent"], t["open_portfolio_percent"], t["close_portfolio_percent"])
            self.cursor.execute("""
            SELECT id FROM trades WHERE date=? AND ticker=? AND open_lots=? AND close_lots=? AND open_price=? AND close_price=?
            """, (t["date"], t["ticker"], t["open_lots"], t["close_lots"], t["open_price"], t["close_price"]))
            exists = self.cursor.fetchone()
            if exists:
                continue
            self.cursor.execute("""
            INSERT INTO trades (date, ticker, open_lots, open_price, open_portfolio_percent,
                                close_lots, close_price, close_portfolio_percent, result, operation_type, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (t["date"], t["ticker"], t["open_lots"], t["open_price"], t["open_portfolio_percent"],
                  t["close_lots"], t["close_price"], t["close_portfolio_percent"], result_str, t["operation_type"], t["notes"]))
        self.conn.commit()

        self.load_processed_data()
        self.calculate_average_results()
        messagebox.showinfo("Готово", "Обработка завершена.")

    def aggregate_by_day(self):
        self.data["Type"] = self.data["Операция"].map(lambda x: "buy" if x.strip().lower() == "покупка" else "sell")
        self.data["Day"] = self.data["Дата сделки"].dt.date

        agg_list = []
        for (ticker, day, ttype), group in self.data.groupby(["Название инструмента", "Day", "Type"]):
            total_lots = group["Количество"].sum()
            weighted_price = (group["Количество"]*group["Цена"]).sum()/total_lots
            agg_list.append({
                "ticker": ticker.strip() if pd.notna(ticker) else "-",
                "date": day,
                "type": ttype,
                "lots": total_lots,
                "price": weighted_price
            })
        agg_df = pd.DataFrame(agg_list)
        if agg_df.empty:
            return agg_df
        agg_df = agg_df.sort_values(["ticker","date"]).reset_index(drop=True)
        return agg_df

    def build_positions_and_close(self, agg_df, portfolio_balance):
        closed_trades = []
        if agg_df.empty:
            return closed_trades

        positions = {}

        for _, row in agg_df.iterrows():
            ticker = row["ticker"]
            date = row["date"]
            is_buy = (row["type"] == "buy")
            qty = row["lots"]
            price = row["price"]

            if ticker not in positions:
                op_type = "long" if is_buy else "short"
                new_qty = qty if is_buy else -qty
                positions[ticker] = {
                    "qty": new_qty,
                    "avg_price": price,
                    "operation_type": op_type,
                    "start_date": date
                }
                continue

            pos = positions[ticker]
            current_qty = pos["qty"]
            current_avg = pos["avg_price"]
            current_op = pos["operation_type"]
            start_date = pos["start_date"]

            if current_op == "long":
                if is_buy:
                    total_val = current_qty*current_avg + qty*price
                    new_qty = current_qty + qty
                    new_avg = total_val/new_qty
                    pos["qty"] = new_qty
                    pos["avg_price"] = new_avg
                else:
                    to_close = qty
                    if to_close < current_qty:
                        closed_trades.append(self.close_one_shot("long", start_date, date, to_close,
                            pos["avg_price"], price, portfolio_balance, ticker))
                        pos["qty"] = current_qty - to_close
                    elif to_close == current_qty:
                        closed_trades.append(self.close_one_shot("long", start_date, date, to_close,
                            pos["avg_price"], price, portfolio_balance, ticker))
                        pos["qty"] = 0
                    else:
                        closed_trades.append(self.close_one_shot("long", start_date, date, current_qty,
                            pos["avg_price"], price, portfolio_balance, ticker))
                        leftover = to_close - current_qty
                        pos["qty"] = -leftover
                        pos["avg_price"] = price
                        pos["operation_type"] = "short"
                        pos["start_date"] = date

            else:
                # short
                if not is_buy:
                    old_qty = pos["qty"]
                    new_qty = old_qty - qty
                    total_val = abs(old_qty)*current_avg + qty*price
                    new_avg = total_val/abs(new_qty)
                    pos["qty"] = new_qty
                    pos["avg_price"] = new_avg
                else:
                    to_close = qty
                    old_qty = pos["qty"]
                    abs_qty = abs(old_qty)
                    if to_close < abs_qty:
                        closed_trades.append(self.close_one_shot("short", start_date, date, to_close,
                            pos["avg_price"], price, portfolio_balance, ticker))
                        pos["qty"] = old_qty + to_close
                    elif to_close == abs_qty:
                        closed_trades.append(self.close_one_shot("short", start_date, date, abs_qty,
                            pos["avg_price"], price, portfolio_balance, ticker))
                        pos["qty"] = 0
                    else:
                        closed_trades.append(self.close_one_shot("short", start_date, date, abs_qty,
                            pos["avg_price"], price, portfolio_balance, ticker))
                        leftover = to_close - abs_qty
                        pos["qty"] = leftover
                        pos["avg_price"] = price
                        pos["operation_type"] = "long"
                        pos["start_date"] = date

        return closed_trades

    def close_one_shot(self, op_type, start_date, end_date, closed_lots, open_price, close_price, portfolio_balance, ticker):
        if op_type == "long":
            price_change_percent = ((close_price - open_price)/open_price)*100.0
        else:
            price_change_percent = ((open_price - close_price)/open_price)*100.0

        open_sum = open_price*closed_lots
        close_sum = close_price*closed_lots
        open_pp = (open_sum/portfolio_balance)*100.0
        close_pp = (close_sum/portfolio_balance)*100.0

        if start_date == end_date:
            date_str = end_date.strftime("%d.%m.%Y")
        else:
            date_str = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"

        return {
            "date": date_str,
            "ticker": ticker,
            "open_lots": closed_lots,
            "open_price": open_price,
            "open_portfolio_percent": open_pp,
            "close_lots": closed_lots,
            "close_price": close_price,
            "close_portfolio_percent": close_pp,
            "price_change_percent": price_change_percent,
            "portfolio_change_percent": 0.0,
            "operation_type": op_type,
            "notes": ""
        }

    def format_result(self, price_change_percent, portfolio_change_percent, open_pp, close_pp):
        sign_price = "+" if price_change_percent > 0 else "-"
        avg_pp = (open_pp + close_pp)/2.0
        return f"{sign_price}{abs(price_change_percent):.2f}% | {avg_pp:.2f}%"

    def load_processed_data(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        self.cursor.execute("SELECT id, date, ticker, open_lots, open_price, open_portfolio_percent,"
                            "close_lots, close_price, close_portfolio_percent, result, operation_type, notes "
                            "FROM trades ORDER BY id ASC")
        rows = self.cursor.fetchall()

        for i, r in enumerate(rows):
            tid = r[0]
            date_val = r[1]
            ticker_val = r[2]
            open_lots = r[3]
            open_price = r[4]
            open_pp = r[5]
            close_lots = r[6]
            close_price = r[7]
            close_pp = r[8]
            result_str = r[9]
            operation_type = r[10]
            notes_val = r[11]

            if operation_type == "long":
                open_sign = "+"
                close_sign = "-"
            else:
                open_sign = "-"
                close_sign = "+"

            open_str = f"{open_sign}{int(open_lots)} | {open_price:.2f} | {open_pp:.2f}%"
            close_str = f"{close_sign}{int(close_lots)} | {close_price:.2f} | {close_pp:.2f}%"

            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", iid=tid, values=(date_val, ticker_val, open_str, close_str, result_str, notes_val), tags=(tag,))

    def calculate_average_results(self):
        self.cursor.execute("SELECT date, result FROM trades")
        rows = self.cursor.fetchall()

        data = []
        for (date_str, result) in rows:
            try:
                if " - " in date_str:
                    start_date_str = date_str.split(" - ")[0].strip()
                    date_p = datetime.strptime(start_date_str, "%d.%m.%Y")
                else:
                    date_p = datetime.strptime(date_str, "%d.%m.%Y")
            except:
                continue
            percent_change, turnover_percent = 0.0, 0.0
            if isinstance(result, str) and "|" in result:
                parts = result.split("|")
                if len(parts) >= 2:
                    p1 = parts[0].strip().replace("%","").replace(",",".")
                    p2 = parts[1].strip().replace("%","").replace(",",".")
                    if p1.startswith("+"):
                        pc = float(p1[1:])
                    else:
                        pc = -float(p1[1:])
                    tp = float(p2)
                    percent_change = pc
                    turnover_percent = tp
            data.append({"Дата": date_p, "Изменение %": percent_change, "Оборот %": turnover_percent})

        if not data:
            for k in self.average_results:
                self.average_results[k].set("—")
            return

        df = pd.DataFrame(data)
        if df.empty:
            for k in self.average_results:
                self.average_results[k].set("—")
            return

        latest_date = df["Дата"].max()
        periods = {
            "День": latest_date,
            "Неделя": latest_date - pd.Timedelta(days=7),
            "Месяц": latest_date - pd.Timedelta(days=30),
            "Квартал": latest_date - pd.Timedelta(days=90),
            "Год": latest_date - pd.Timedelta(days=365),
        }

        for period, start_date in periods.items():
            filtered = df[df["Дата"] >= start_date]
            if not filtered.empty:
                avg_change = filtered["Изменение %"].mean()
                total_turnover = filtered["Оборот %"].sum()
                sign_avg = "+" if avg_change > 0 else "-"
                self.average_results[period].set(f"{sign_avg}{abs(avg_change):.2f}% | {abs(total_turnover):.2f}%")
            else:
                self.average_results[period].set("—")

    def delete_selected_trade(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Сначала выберите сделку для удаления.")
            return
        if len(selected) > 1:
            messagebox.showwarning("Внимание", "Выберите только одну сделку.")
            return
        tid = selected[0]
        item = self.tree.item(tid)
        date_val, ticker_val = item["values"][0], item["values"][1]
        confirm = messagebox.askyesno("Подтверждение", f"Удалить сделку {ticker_val} от {date_val}?")
        if confirm:
            self.cursor.execute("DELETE FROM trades WHERE id = ?", (tid,))
            self.conn.commit()
            self.load_processed_data()
            self.calculate_average_results()
            messagebox.showinfo("Успех", "Сделка удалена.")

    def clear_table(self):
        confirm = messagebox.askyesno("Подтверждение", "Удалить все сделки?")
        if confirm:
            self.cursor.execute("DELETE FROM trades")
            self.conn.commit()
            self.load_processed_data()
            self.calculate_average_results()
            messagebox.showinfo("Успех", "Таблица очищена.")

    def add_manual_trade(self):
        date_str = simpledialog.askstring("Дата", "Введите дату (дд.мм.гггг):")
        ticker = simpledialog.askstring("Тикер", "Введите тикер:")
        if not date_str or not ticker:
            messagebox.showwarning("Ошибка", "Дата и тикер обязательны.")
            return
        notes = simpledialog.askstring("Примечания", "Введите примечания:")
        try:
            date = datetime.strptime(date_str, "%d.%m.%Y").strftime("%d.%m.%Y")
        except:
            messagebox.showwarning("Ошибка", "Некорректный формат даты.")
            return

        open_lots = 100
        open_price = 10.0
        open_pp = (open_lots * open_price / max(self.current_balance,1))*100
        result = "-"
        operation_type = "long"

        self.cursor.execute("""
        INSERT INTO trades (date, ticker, open_lots, open_price, open_portfolio_percent,
                            close_lots, close_price, close_portfolio_percent, result, operation_type, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, ticker.strip(), open_lots, open_price, open_pp, None, None, None, result, operation_type, notes or "-"))
        self.conn.commit()
        self.load_processed_data()
        self.calculate_average_results()
        messagebox.showinfo("Успех", "Сделка добавлена.")

    def edit_comment(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        col_index = int(col.replace("#","")) - 1
        if col_index != 5:
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        item = self.tree.item(row_id)
        current_comment = item["values"][5]
        new_comment = simpledialog.askstring("Редактировать примечание", "Введите новый комментарий:", initialvalue=current_comment)
        if new_comment is not None:
            trade_id = row_id
            self.cursor.execute("UPDATE trades SET notes = ? WHERE id = ?", (new_comment, trade_id))
            self.conn.commit()
            vals = list(item["values"])
            vals[5] = new_comment
            self.tree.item(row_id, values=vals)
            messagebox.showinfo("Успех", "Примечание обновлено.")

    def sort_by_date(self):
        self.cursor.execute("SELECT id, date, ticker, open_lots, open_price, open_portfolio_percent,"
                            "close_lots, close_price, close_portfolio_percent, result, operation_type, notes FROM trades")
        rows = self.cursor.fetchall()

        def parse_start_date(dstr):
            if " - " in dstr:
                part = dstr.split(" - ")[0].strip()
                return datetime.strptime(part, "%d.%m.%Y")
            else:
                return datetime.strptime(dstr.strip(), "%d.%m.%Y")

        rows = sorted(rows, key=lambda r: parse_start_date(r[1]), reverse=(not self.date_sort_ascending))
        self.date_sort_ascending = not self.date_sort_ascending

        for i in self.tree.get_children():
            self.tree.delete(i)

        for i, r in enumerate(rows):
            tid = r[0]
            date_val = r[1]
            ticker_val = r[2]
            open_lots = r[3]
            open_price = r[4]
            open_pp = r[5]
            close_lots = r[6]
            close_price = r[7]
            close_pp = r[8]
            result_str = r[9]
            operation_type = r[10]
            notes_val = r[11]

            if operation_type == "long":
                open_sign = "+"
                close_sign = "-"
            else:
                open_sign = "-"
                close_sign = "+"

            open_str = f"{open_sign}{int(open_lots)} | {open_price:.2f} | {open_pp:.2f}%"
            close_str = f"{close_sign}{int(close_lots)} | {close_price:.2f} | {close_pp:.2f}%"

            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", iid=tid, values=(date_val, ticker_val, open_str, close_str, result_str, notes_val), tags=(tag,))


if __name__ == "__main__":
    root = tk.Tk()
    app = TradeApp(root)
    root.mainloop()
