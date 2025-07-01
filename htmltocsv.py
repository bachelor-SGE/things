from bs4 import BeautifulSoup
import pandas as pd
import re
from tkinter import Tk, filedialog

def extract_total_sum(soup):
    """
    Извлечение итоговой суммы из блока 'ИТОГО оценка состояния счета (руб.)'.
    """
    # Найти строку с текстом "ИТОГО оценка состояния счета (руб.)"
    total_row = None
    for row in soup.find_all('tr'):
        if "ИТОГО оценка состояния счета (руб.)" in row.get_text():
            total_row = row
            break

    # Проверяем, нашли ли нужную строку
    if total_row is None:
        print("Не найден блок 'ИТОГО оценка состояния счета (руб.)'")
        return None

    # Берем следующую строку, где находится итоговая сумма
    next_row = total_row.find_next('tr')
    if next_row:
        cells = next_row.find_all('td')  # Находим все ячейки строки
        if cells:
            return cells[-1].get_text(strip=True)  # Возвращаем значение из последней ячейки
    return None

def extract_trades(soup):
    """
    Извлечение строк с данными о сделках.
    """
    rows = soup.find_all('tr')  # Находим все строки таблиц
    data = []
    date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')  # Шаблон для поиска даты

    for row in rows:
        cells = row.find_all('td')  # Ячейки строки
        row_text = [cell.get_text(strip=True) for cell in cells]

        # Проверяем наличие даты
        if any(date_pattern.match(cell) for cell in row_text):
            # Проверяем наличие тикера (названия инструмента)
            instrument = row_text[2] if len(row_text) > 2 else ""
            operation = row_text[4] if len(row_text) > 4 else ""

            # Если инструмент - фьючерс, извлекаем код из соседнего блока
            if "Фьючерсы, Расчетный" in instrument:
                instrument = row_text[3] if len(row_text) > 3 else ""

            if instrument:  # Если инструмент указан
                data.append({
                    "Дата сделки": row_text[0],
                    "Время сделки": row_text[1] if len(row_text) > 1 else "",
                    "Название инструмента": instrument,
                    "Операция": operation,
                    "Количество": row_text[5] if len(row_text) > 5 else "",
                    "Цена": row_text[6] if len(row_text) > 6 else ""
                })

    trades_df = pd.DataFrame(data)

    # Фильтрация данных: оставляем только строки с операциями "Покупка" или "Продажа"
    trades_df = trades_df[trades_df["Операция"].isin(["Покупка", "Продажа"])]

    return trades_df

def main():
    # Создаем окно для выбора файла
    root = Tk()
    root.withdraw()  # Прячем главное окно

    # Выбор HTML-файла
    file_path = filedialog.askopenfilename(
        title="Выберите HTML-файл",
        filetypes=(("HTML files", "*.html"), ("All files", "*.*"))
    )
    if not file_path:
        print("Файл не выбран. Завершение работы.")
        return

    # Открытие HTML-файла
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Парсим HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # Извлекаем итоговую сумму
    total_sum = extract_total_sum(soup)
    if total_sum:
        print(f"Итоговая сумма: {total_sum}")
    else:
        print("Итоговая сумма не найдена.")

    # Извлекаем сделки
    trades_df = extract_trades(soup)

    # Выбор пути для сохранения
    save_path = filedialog.asksaveasfilename(
        title="Сохранить файл как",
        defaultextension=".xlsx",
        filetypes=(("Excel files", "*.xlsx"), ("All files", "*.*"))
    )
    if not save_path:
        print("Путь для сохранения не выбран. Завершение работы.")
        return

    # Сохраняем данные в Excel
    with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
        trades_df.to_excel(writer, index=False, sheet_name='Сделки')
        # Добавляем итоговую сумму на отдельный лист
        if total_sum:
            pd.DataFrame([{"Итоговая сумма": total_sum}]).to_excel(
                writer, index=False, sheet_name='Итог'
            )

    print(f"Данные успешно сохранены в файл {save_path}")

if __name__ == "__main__":
    main()
