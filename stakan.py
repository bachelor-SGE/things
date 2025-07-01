import tkinter as tk
import threading
import time
import re
import requests
import xml.etree.ElementTree as ET

import pyautogui
import pytesseract
from PIL import Image

# Если Tesseract не находится в PATH, укажите его полный путь:
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Конфигурации для OCR:
# Для зон с ценами – разрешаем цифры и знаки, используемые в ценах
CONFIG_PRICE = "--psm 6 -c tessedit_char_whitelist=0123456789.,:"
# Для зон с лотами – разрешаем только цифры (так как лоты, как правило, целые числа)
CONFIG_NUMBERS = "--psm 6 -c tessedit_char_whitelist=0123456789"

def get_usd_rate():
    """
    Получает актуальный курс доллара (USD) по данным ЦБ.
    """
    try:
        response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp")
        if response.status_code == 200:
            tree = ET.fromstring(response.content)
            for valute in tree.findall("Valute"):
                char_code = valute.find("CharCode").text
                if char_code == "USD":
                    value_str = valute.find("Value").text.replace(",", ".")
                    return float(value_str)
    except Exception as e:
        print("Ошибка при получении курса USD:", e)
    return None

def calculate_vwap_by_sum(order_list, target_sum, lot_multiplier=1):
    """
    Рассчитывает средневзвешенную цену для покупки на указанную сумму.
    """
    accumulated_cost = 0.0
    accumulated_volume = 0.0

    for price, volume in order_list:
        effective_price = price * lot_multiplier
        cost = effective_price * volume
        if accumulated_cost + cost >= target_sum:
            needed_cost = target_sum - accumulated_cost
            volume_needed = needed_cost / effective_price
            accumulated_volume += volume_needed
            accumulated_cost += needed_cost
            break
        else:
            accumulated_cost += cost
            accumulated_volume += volume

    if accumulated_cost < target_sum:
        return None, None, None
    average_price = accumulated_cost / accumulated_volume
    return average_price, accumulated_volume, accumulated_cost

def calculate_vwap(order_list, target_volume, lot_multiplier=1):
    """
    Рассчитывает средневзвешенную цену для указанного объёма.
    """
    accumulated_volume = 0.0
    total_value = 0.0

    for price, volume in order_list:
        effective_price = price * lot_multiplier
        if accumulated_volume + volume >= target_volume:
            needed = target_volume - accumulated_volume
            total_value += effective_price * needed
            accumulated_volume += needed
            break
        else:
            total_value += effective_price * volume
            accumulated_volume += volume

    if accumulated_volume < target_volume:
        return None, None
    effective_price_result = total_value / target_volume
    return effective_price_result, total_value

def calculate_break_even_volume(buy_price, sell_orders, target_volume, lot_multiplier=1):
    """
    Вычисляет дополнительный объём (в лотах), необходимый для выхода в ноль.
    """
    accumulated_volume = 0.0
    total_sale_value = 0.0

    for price, volume in sell_orders:
        effective_price = price * lot_multiplier
        if accumulated_volume + volume >= target_volume:
            needed = target_volume - accumulated_volume
            total_sale_value += effective_price * needed
            accumulated_volume += needed
            break
        else:
            total_sale_value += effective_price * volume
            accumulated_volume += volume

    required_value = buy_price * target_volume
    if total_sale_value >= required_value:
        return 0.0, total_sale_value / target_volume
    else:
        shortfall_value = required_value - total_sale_value
        additional_volume_needed = shortfall_value / buy_price
        effective_sell_price = total_sale_value / target_volume
        return additional_volume_needed, effective_sell_price

def clean_number(num_str):
    """
    Очищает строку с числом от распространённых ошибок OCR:
      - Заменяет буквы, похожие на цифры:
          'I' и 'l' -> '1',
          'O' -> '0',
          'B' -> '8'.
      - Заменяет двоеточия на точки.
      - Удаляет пробелы.
      - Заменяет запятые на точки.
      - Если обнаружено более одной точки, оставляет только первую.
    """
    num_str = num_str.replace("I", "1").replace("l", "1").replace("O", "0").replace("B", "8")
    num_str = num_str.replace(":", ".")
    num_str = num_str.replace(" ", "")
    num_str = num_str.replace(",", ".")
    
    parts = num_str.split('.')
    if len(parts) > 2:
        num_str = parts[0] + '.' + ''.join(parts[1:])
    return num_str

def parse_numbers(text):
    """
    Извлекает из текста последовательности символов, которые могут быть числовыми.
    Используется регулярное выражение, учитывающее возможные ошибки OCR.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numbers = []
    # Регулярное выражение учитывает буквы I, l, O, B
    pattern = r"[0-9IiLlOoB\.,:]+"
    for line in lines:
        candidates = re.findall(pattern, line)
        for candidate in candidates:
            cleaned = clean_number(candidate)
            try:
                value = float(cleaned)
                numbers.append(value)
            except ValueError:
                continue
    return numbers

class ScreenSelector(tk.Toplevel):
    """
    Открывает полноэкранное окно для выбора области экрана.
    Пользователь выделяет прямоугольник, после чего вызывается callback с координатами (x, y, width, height).
    """
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.rect = None

        self.overrideredirect(True)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")

        try:
            self.attributes("-alpha", 0.3)
        except Exception as e:
            print("Атрибут прозрачности не поддерживается:", e)

        self.config(bg="black")
        self.canvas = tk.Canvas(self, cursor="cross", bg="black")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y,
                                                   outline="red", width=2)

    def on_mouse_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_button_release(self, event):
        end_x, end_y = event.x, event.y
        x = min(self.start_x, end_x)
        y = min(self.start_y, end_y)
        width = abs(end_x - self.start_x)
        height = abs(end_y - self.start_y)
        self.callback(x, y, width, height)
        self.destroy()

class OrderBookApp(tk.Tk):
    """
    Основное окно приложения.

    Реализована возможность выделения 4-х зон:
      - ASKS: Цена
      - ASKS: Лоты
      - BIDS: Цена
      - BIDS: Лоты

    После выделения зон производится OCR, из каждой области извлекаются числа, и формируются пары (цена, лоты).
    Далее рассчитываются показатели (VWAP, объем покупки, break-even и т.д.), а результаты выводятся на экран.
    Также отображаются "сырые" OCR-данные для каждой зоны и объединённые разобранные данные ордербука.
    """
    def __init__(self):
        super().__init__()
        self.title("Order Book Analyzer")
        self.geometry("950x1200")

        # Поля ввода параметров ордера (сумма, позиции в лоте)
        tk.Label(self, text="Введите сумму ордера (в рублях):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.target_entry = tk.Entry(self)
        self.target_entry.grid(row=0, column=1, padx=5, pady=5)
        self.target_entry.insert(0, "100000")

        tk.Label(self, text="Позиции в лоте:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.lot_entry = tk.Entry(self)
        self.lot_entry.grid(row=0, column=3, padx=5, pady=5)
        self.lot_entry.insert(0, "1")

        self.usd_var = tk.BooleanVar(value=False)
        self.usd_checkbox = tk.Checkbutton(self, text="Актив торгуется в долларах", variable=self.usd_var)
        self.usd_checkbox.grid(row=0, column=4, padx=5, pady=5, sticky="w")

        # Кнопки для выбора областей (4 зоны)
        # ASKS: Цена
        self.asks_price_region = None
        self.asks_price_button = tk.Button(self, text="Выбрать область ASKS (Цена)", command=self.select_asks_price)
        self.asks_price_button.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.asks_price_label = tk.Label(self, text="Область не выбрана")
        self.asks_price_label.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # ASKS: Лоты
        self.asks_lots_region = None
        self.asks_lots_button = tk.Button(self, text="Выбрать область ASKS (Лоты)", command=self.select_asks_lots)
        self.asks_lots_button.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.asks_lots_label = tk.Label(self, text="Область не выбрана")
        self.asks_lots_label.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # BIDS: Цена
        self.bids_price_region = None
        self.bids_price_button = tk.Button(self, text="Выбрать область BIDS (Цена)", command=self.select_bids_price)
        self.bids_price_button.grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.bids_price_label = tk.Label(self, text="Область не выбрана")
        self.bids_price_label.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        # BIDS: Лоты
        self.bids_lots_region = None
        self.bids_lots_button = tk.Button(self, text="Выбрать область BIDS (Лоты)", command=self.select_bids_lots)
        self.bids_lots_button.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.bids_lots_label = tk.Label(self, text="Область не выбрана")
        self.bids_lots_label.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Кнопка запуска анализа
        self.start_button = tk.Button(self, text="Старт анализа", command=self.start_analysis)
        self.start_button.grid(row=5, column=0, columnspan=2, padx=5, pady=5)

        # Поле для вывода результатов расчётов
        self.results_text = tk.Text(self, width=90, height=10)
        self.results_text.grid(row=6, column=0, columnspan=5, padx=5, pady=5)

        # Текстовые поля для вывода "сырого" OCR-данных для каждой зоны
        tk.Label(self, text="OCR ASKS (Цена):").grid(row=7, column=0, columnspan=5, sticky="w", padx=5)
        self.ocr_asks_price_text = tk.Text(self, width=90, height=5)
        self.ocr_asks_price_text.grid(row=8, column=0, columnspan=5, padx=5, pady=5)

        tk.Label(self, text="OCR ASKS (Лоты):").grid(row=9, column=0, columnspan=5, sticky="w", padx=5)
        self.ocr_asks_lots_text = tk.Text(self, width=90, height=5)
        self.ocr_asks_lots_text.grid(row=10, column=0, columnspan=5, padx=5, pady=5)

        tk.Label(self, text="OCR BIDS (Цена):").grid(row=11, column=0, columnspan=5, sticky="w", padx=5)
        self.ocr_bids_price_text = tk.Text(self, width=90, height=5)
        self.ocr_bids_price_text.grid(row=12, column=0, columnspan=5, padx=5, pady=5)

        tk.Label(self, text="OCR BIDS (Лоты):").grid(row=13, column=0, columnspan=5, sticky="w", padx=5)
        self.ocr_bids_lots_text = tk.Text(self, width=90, height=5)
        self.ocr_bids_lots_text.grid(row=14, column=0, columnspan=5, padx=5, pady=5)

        # Текстовые поля для отображения объединённых (parsed) данных ордербука
        tk.Label(self, text="Parsed ASKS (Цена за лот | Лоты):").grid(row=15, column=0, columnspan=5, sticky="w", padx=5)
        self.parsed_asks_text = tk.Text(self, width=90, height=5)
        self.parsed_asks_text.grid(row=16, column=0, columnspan=5, padx=5, pady=5)

        tk.Label(self, text="Parsed BIDS (Цена за лот | Лоты):").grid(row=17, column=0, columnspan=5, sticky="w", padx=5)
        self.parsed_bids_text = tk.Text(self, width=90, height=5)
        self.parsed_bids_text.grid(row=18, column=0, columnspan=5, padx=5, pady=5)

        self.running = False

    # Функции для выбора зон:
    def select_asks_price(self):
        self.wait_window(ScreenSelector(self.set_asks_price_region))

    def set_asks_price_region(self, x, y, width, height):
        self.asks_price_region = (x, y, width, height)
        self.asks_price_label.config(text=f"ASKS (Цена): x={x}, y={y}, w={width}, h={height}")

    def select_asks_lots(self):
        self.wait_window(ScreenSelector(self.set_asks_lots_region))

    def set_asks_lots_region(self, x, y, width, height):
        self.asks_lots_region = (x, y, width, height)
        self.asks_lots_label.config(text=f"ASKS (Лоты): x={x}, y={y}, w={width}, h={height}")

    def select_bids_price(self):
        self.wait_window(ScreenSelector(self.set_bids_price_region))

    def set_bids_price_region(self, x, y, width, height):
        self.bids_price_region = (x, y, width, height)
        self.bids_price_label.config(text=f"BIDS (Цена): x={x}, y={y}, w={width}, h={height}")

    def select_bids_lots(self):
        self.wait_window(ScreenSelector(self.set_bids_lots_region))

    def set_bids_lots_region(self, x, y, width, height):
        self.bids_lots_region = (x, y, width, height)
        self.bids_lots_label.config(text=f"BIDS (Лоты): x={x}, y={y}, w={width}, h={height}")

    def start_analysis(self):
        # Проверяем, что все 4 области выбраны
        if (self.asks_price_region is None or self.asks_lots_region is None or
                self.bids_price_region is None or self.bids_lots_region is None):
            self.update_results("Ошибка: выберите все 4 области (ASKS: Цена, ASKS: Лоты, BIDS: Цена, BIDS: Лоты)!\n")
            return

        try:
            target_sum = float(self.target_entry.get())
        except ValueError:
            self.update_results("Ошибка: некорректное значение суммы ордера.\n")
            return

        try:
            lot_multiplier = float(self.lot_entry.get())
        except ValueError:
            lot_multiplier = 1.0

        if not self.running:
            self.running = True
            analysis_thread = threading.Thread(target=self.analysis_loop, args=(target_sum, lot_multiplier), daemon=True)
            analysis_thread.start()

    def analysis_loop(self, target_sum, lot_multiplier):
        while self.running:
            result = "Результаты анализа:\n"
            result += "--------------------------\n"

            try:
                # Получаем скриншоты для каждой из 4 зон:
                asks_price_img = pyautogui.screenshot(region=self.asks_price_region)
                asks_lots_img = pyautogui.screenshot(region=self.asks_lots_region)
                bids_price_img = pyautogui.screenshot(region=self.bids_price_region)
                bids_lots_img = pyautogui.screenshot(region=self.bids_lots_region)
            except Exception as e:
                result += f"Ошибка при снятии скриншотов: {e}\n"
                self.update_results(result)
                time.sleep(2)
                continue

            # Выполняем OCR для каждой зоны:
            # Для цен используем CONFIG_PRICE, для лотов – CONFIG_NUMBERS.
            raw_asks_price_text = pytesseract.image_to_string(asks_price_img, lang="eng", config=CONFIG_PRICE)
            raw_asks_lots_text = pytesseract.image_to_string(asks_lots_img, lang="eng", config=CONFIG_NUMBERS)
            raw_bids_price_text = pytesseract.image_to_string(bids_price_img, lang="eng", config=CONFIG_PRICE)
            raw_bids_lots_text = pytesseract.image_to_string(bids_lots_img, lang="eng", config=CONFIG_NUMBERS)

            # Обновляем поля с "сырыми" OCR-данными:
            self.update_ocr_text(raw_asks_price_text, raw_asks_lots_text, raw_bids_price_text, raw_bids_lots_text)

            # Извлекаем числа из каждой области:
            asks_price_list = parse_numbers(raw_asks_price_text)
            asks_lots_list = parse_numbers(raw_asks_lots_text)
            bids_price_list = parse_numbers(raw_bids_price_text)
            bids_lots_list = parse_numbers(raw_bids_lots_text)

            # Формируем пары (цена, лоты) для каждого стакана:
            asks_orders = list(zip(asks_price_list, asks_lots_list))
            bids_orders = list(zip(bids_price_list, bids_lots_list))

            # Обновляем поле с объединёнными (parsed) данными:
            self.update_parsed_text(asks_orders, bids_orders)

            # Производим расчёты для ASKS (покупка)
            buy_price = None
            acquired_volume = None
            total_cost = None
            if not asks_orders:
                result += "Не удалось распознать данные ASKS.\n"
            else:
                if self.usd_var.get():
                    usd_rate = get_usd_rate()
                    if usd_rate is None:
                        result += "Не удалось получить курс USD из ЦБ.\n"
                        time.sleep(2)
                        continue
                    target_sum_converted = target_sum / usd_rate  # Сумма в долларах
                    buy_price, acquired_volume, total_cost = calculate_vwap_by_sum(asks_orders, target_sum_converted, lot_multiplier)
                    if buy_price is None:
                        result += "Недостаточно ликвидности в ASKS для покупки указанной суммы.\n"
                    else:
                        buy_price_rub = buy_price * usd_rate
                        result += f"Средневзвешенная цена покупки (ASKS) для лота: {buy_price_rub:.2f} руб.\n"
                        result += f"Объем, приобретаемый за {target_sum:.2f} руб.: {acquired_volume:.2f} лотов.\n"
                else:
                    buy_price, acquired_volume, total_cost = calculate_vwap_by_sum(asks_orders, target_sum, lot_multiplier)
                    if buy_price is None:
                        result += "Недостаточно ликвидности в ASKS для покупки указанной суммы.\n"
                    else:
                        result += f"Средневзвешенная цена покупки (ASKS) для лота: {buy_price:.2f} руб.\n"
                        result += f"Объем, приобретаемый за {target_sum:.2f} руб.: {acquired_volume:.2f} лотов.\n"

            # Производим расчёты для BIDS (продажа)
            if not bids_orders:
                result += "Не удалось распознать данные BIDS.\n"
            else:
                if acquired_volume is not None:
                    sell_price, _ = calculate_vwap(bids_orders, acquired_volume, lot_multiplier)
                    if sell_price is None:
                        result += "Недостаточно ликвидности в BIDS для продажи приобретенного объёма.\n"
                    else:
                        if self.usd_var.get():
                            sell_price_rub = sell_price * usd_rate
                            result += f"Средневзвешенная цена продажи (BIDS) для лота: {sell_price_rub:.2f} руб.\n"
                        else:
                            result += f"Средневзвешенная цена продажи (BIDS) для лота: {sell_price:.2f} руб.\n"
                    additional_volume, current_sell_vwap = calculate_break_even_volume(buy_price, bids_orders, acquired_volume, lot_multiplier)
                    if additional_volume is not None:
                        if self.usd_var.get():
                            current_sell_vwap_rub = current_sell_vwap * usd_rate
                            result += f"Текущая VWAP для продажи (лота): {current_sell_vwap_rub:.2f} руб.\n"
                        else:
                            result += f"Текущая VWAP для продажи (лота): {current_sell_vwap:.2f} руб.\n"
                        if additional_volume > 0:
                            effective_buy = buy_price * (usd_rate if self.usd_var.get() else 1)
                            result += (f"Для выхода в ноль (при цене {effective_buy:.2f} руб.) "
                                       f"необходимо дождаться дополнительного объёма примерно {additional_volume:.2f} лотов.\n")
                        else:
                            result += "При продаже приобретенного объёма вы уже выходите в ноль или выше.\n"
            self.update_results(result)
            time.sleep(2)

    def update_results(self, text):
        def inner():
            self.results_text.delete(1.0, tk.END)
            self.results_text.insert(tk.END, text)
        self.after(0, inner)

    def update_ocr_text(self, asks_price_raw, asks_lots_raw, bids_price_raw, bids_lots_raw):
        def inner():
            self.ocr_asks_price_text.delete(1.0, tk.END)
            self.ocr_asks_price_text.insert(tk.END, asks_price_raw)
            self.ocr_asks_lots_text.delete(1.0, tk.END)
            self.ocr_asks_lots_text.insert(tk.END, asks_lots_raw)
            self.ocr_bids_price_text.delete(1.0, tk.END)
            self.ocr_bids_price_text.insert(tk.END, bids_price_raw)
            self.ocr_bids_lots_text.delete(1.0, tk.END)
            self.ocr_bids_lots_text.insert(tk.END, bids_lots_raw)
        self.after(0, inner)

    def update_parsed_text(self, asks_orders, bids_orders):
        def inner():
            self.parsed_asks_text.delete(1.0, tk.END)
            self.parsed_bids_text.delete(1.0, tk.END)
            if asks_orders:
                asks_str = "Цена за лот\tЛоты\n"
                asks_str += "\n".join([f"{price:.4f}\t\t{volume}" for price, volume in asks_orders])
            else:
                asks_str = "Нет данных"
            if bids_orders:
                bids_str = "Цена за лот\tЛоты\n"
                bids_str += "\n".join([f"{price:.4f}\t\t{volume}" for price, volume in bids_orders])
            else:
                bids_str = "Нет данных"
            self.parsed_asks_text.insert(tk.END, asks_str)
            self.parsed_bids_text.insert(tk.END, bids_str)
        self.after(0, inner)

if __name__ == "__main__":
    app = OrderBookApp()
    app.mainloop()
