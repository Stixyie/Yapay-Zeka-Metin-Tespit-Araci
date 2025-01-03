import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, scrolledtext
import google.generativeai as genai
import json
import os
import threading
import queue
import time
import re
import signal  # Add this import at the top with other imports
import concurrent.futures  # Add this import at the top

class AIDetector:
    def __init__(self, content_frame):
        self.content_frame = content_frame
        
        # API key configuration
        self.config_file = 'config.json'
        self.api_key = self.load_api_key()
        
        # Initialize Gemini models
        self.available_models = ['gemini-pro']  # Start with basic model
        self.current_model = 'gemini-pro'
        self.model_var = None
        self.model_dropdown = None
        
        # AI özellikleri için JSON dosyası
        self.ai_features_path = 'ai_features.json'
        self.ai_features = self.load_ai_features()
        
        # Analiz durumu için değişkenler
        self.is_analyzing = False
        self.cancel_analysis = False
        self.analysis_thread = None
        self.analysis_queue = queue.Queue()
        
        self.setup_ui()
        
        # If API key exists, start background model validation
        if self.api_key:
            self.start_background_model_validation()

    def load_api_key(self):
        """Load API key from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config.get('api_key')
        except Exception as e:
            print(f"API key yüklenirken hata: {str(e)}")
        return None

    def save_api_key(self, api_key):
        """Save API key to config file"""
        try:
            config = {'api_key': api_key}
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
            return True
        except Exception as e:
            print(f"API key kaydedilirken hata: {str(e)}")
            return False

    def validate_and_initialize_api(self):
        """Validate API key and initialize available models"""
        try:
            if not self.api_key or len(self.api_key.strip()) < 10:
                return False
                
            genai.configure(api_key=self.api_key)
            
            # Quick test with minimal configuration
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(
                "test",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1,
                    temperature=0
                )
            )
            
            # API key geçerliyse kaydet ve arka planda model doğrulamasını başlat
            self.save_api_key(self.api_key)
            self.start_background_model_validation()
            return True
            
        except Exception as e:
            self.api_key = None
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            self.show_api_error(str(e))
            return False

    def show_api_error(self, error_message):
        """Show API error and instructions to get a new API key"""
        error_text = (
            "API Anahtarı Hatası!\n\n"
            f"Hata Detayı: {error_message}\n\n"
            "Yeni bir API anahtarı almak için:\n"
            "1. https://aistudio.google.com/apikey adresine gidin\n"
            "2. Google hesabınızla giriş yapın\n"
            "3. 'Get API key' butonuna tıklayın\n"
            "4. Yeni bir API anahtarı oluşturun\n"
            "5. Oluşturulan API anahtarını kopyalayın\n"
            "6. Programda 'API Anahtarı Ayarla' butonuna tıklayıp yapıştırın"
        )
        messagebox.showerror("API Hatası", error_text)
        self.api_key = None

    def check_model_availability(self):
        """Check if current model is available and working"""
        if not self.current_model or not self.api_key:
            return False
            
        try:
            # Quick test with minimal configuration
            model = genai.GenerativeModel(self.current_model)
            response = model.generate_content(
                "test",
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=1,
                    temperature=0
                )
            )
            return True
        except Exception as e:
            print(f"Model availability check failed: {str(e)}")
            return False

    def switch_to_available_model(self):
        """Switch to another available model if current one fails"""
        if not self.available_models:
            self.validate_and_initialize_api()
            
        if self.available_models:
            # Remove current model from available models if it's not working
            if self.current_model in self.available_models:
                self.available_models.remove(self.current_model)
            
            # Try to switch to the next available model
            if self.available_models:
                self.current_model = self.available_models[0]
                if hasattr(self, 'model_var') and self.model_var:
                    self.model_var.set(self.current_model)
                return True
        
        return False

    def on_model_change(self, selection):
        """Handle model selection change"""
        if selection and selection != self.current_model:
            # Show quick loading indicator
            self.model_dropdown.configure(state="disabled")
            self.content_frame.update()
            
            try:
                # Quick availability check
                self.current_model = selection
                if not self.check_model_availability():
                    # Try to switch to another model
                    if not self.switch_to_available_model():
                        messagebox.showwarning(
                            "Model Hatası",
                            "Hiçbir model şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin."
                        )
            finally:
                # Re-enable dropdown
                self.model_dropdown.configure(state="normal")

    def validate_api_key(self, api_key):
        """Quickly validate API key format and test it"""
        # Check basic format first
        if not isinstance(api_key, str):
            return False, "API anahtarı geçersiz format."
            
        # Remove whitespace
        api_key = api_key.strip()
        
        # Check format with regex (AIzaSy followed by 33 characters of base64 url-safe)
        if not re.match(r'^AIzaSy[a-zA-Z0-9_-]{33}$', api_key):
            return False, "API anahtarı geçersiz format. 'AIzaSy' ile başlamalı ve toplam 39 karakter olmalıdır."
            
        try:
            # Configure API
            genai.configure(api_key=api_key)
            
            # Create test function
            def test_api():
                model = genai.GenerativeModel('gemini-pro')
                return model.generate_content(
                    "test",
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=1,
                        temperature=0
                    )
                )

            # Test with timeout using ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(test_api)
                try:
                    future.result(timeout=5)  # 5 second timeout
                except concurrent.futures.TimeoutError:
                    return False, "API doğrulama zaman aşımına uğradı."
                except Exception as e:
                    return False, str(e)
            
            # API key valid, save and return
            self.api_key = api_key
            self.save_api_key(api_key)
            return True, ""
            
        except Exception as e:
            return False, str(e)

    def show_api_instructions(self):
        """Show detailed API key acquisition instructions"""
        instructions = """
Google AI Studio'dan API Anahtarı Alma Adımları:

1. https://aistudio.google.com/apikey adresine gidin

2. Google Hesabı:
   - Google hesabınızla giriş yapın
   - Hesabınız yoksa yeni bir hesap oluşturun

3. API Anahtarı Oluşturma:
   - 'Get API key' veya 'API anahtarı al' butonuna tıklayın
   - Yeni bir proje seçin veya mevcut projeyi kullanın
   - API kullanım koşullarını kabul edin

4. API Anahtarını Kopyalama:
   - Oluşturulan API anahtarını güvenli bir şekilde kopyalayın
   - API anahtarını kimseyle paylaşmayın

5. Önemli Notlar:
   - API anahtarı ücretsizdir
   - Günlük kullanım limitleri vardır
   - API anahtarını güvenli bir yerde saklayın

Not: API anahtarı oluşturduktan sonra tekrar görüntülenemez.
Kaybederseniz yeni bir anahtar oluşturmanız gerekir.
"""
        messagebox.showinfo("API Anahtarı Nasıl Alınır", instructions)

    def setup_api_key_dialog(self):
        """Show API key input dialog with validation"""
        # Create custom dialog instead of using CTkInputDialog
        dialog = ctk.CTkToplevel()
        dialog.title("API Anahtarı")
        dialog.geometry("400x180")
        dialog.transient(self.content_frame)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        # Add label
        label = ctk.CTkLabel(dialog, text="Lütfen Gemini API anahtarınızı girin:", font=("Arial", 14))
        label.pack(pady=(20, 10))
        
        # Add entry with context menu
        entry_frame = ctk.CTkFrame(dialog)
        entry_frame.pack(pady=10, padx=20, fill="x")
        
        entry = tk.Entry(entry_frame, font=("Arial", 12))  # Using tk.Entry for better copy/paste support
        entry.pack(fill="x", pady=5, padx=5, ipady=3)
        
        # Create and bind context menu
        def copy_text():
            dialog.clipboard_clear()
            dialog.clipboard_append(entry.selection_get())
            
        def cut_text():
            copy_text()
            entry.delete("sel.first", "sel.last")
            
        def paste_text():
            try:
                text = dialog.clipboard_get()
                entry.insert("insert", text)
            except:
                pass
                
        def select_all():
            entry.select_range(0, tk.END)
            
        menu = tk.Menu(entry, tearoff=0)
        menu.add_command(label="Kes", command=cut_text)
        menu.add_command(label="Kopyala", command=copy_text)
        menu.add_command(label="Yapıştır", command=paste_text)
        menu.add_separator()
        menu.add_command(label="Tümünü Seç", command=select_all)
        
        def show_menu(event):
            if event.num == 3:  # Right click
                menu.post(event.x_root, event.y_root)
                
        entry.bind("<Button-3>", show_menu)
        
        # Add keyboard shortcuts
        entry.bind("<Control-x>", lambda e: cut_text())
        entry.bind("<Control-c>", lambda e: copy_text())
        entry.bind("<Control-v>", lambda e: paste_text())
        entry.bind("<Control-a>", lambda e: select_all())
        
        # Variable to store result
        result = [None]
        
        def on_ok():
            result[0] = entry.get()
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
        
        # Add buttons with larger size
        button_frame = ctk.CTkFrame(dialog)
        button_frame.pack(pady=(15, 20))
        
        ok_button = ctk.CTkButton(
            button_frame,
            text="Tamam",
            command=on_ok,
            width=120,
            height=35,
            font=("Arial", 13)
        )
        ok_button.pack(side="left", padx=10)
        
        cancel_button = ctk.CTkButton(
            button_frame,
            text="İptal",
            command=on_cancel,
            width=120,
            height=35,
            font=("Arial", 13)
        )
        cancel_button.pack(side="left", padx=10)
        
        # Handle dialog close button
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        # Set focus to entry
        entry.focus_set()
        
        def validate_input(event=None):
            """Validate input as user types"""
            current = entry.get()
            
            # Always allow 'AIzaSy' prefix
            if len(current) <= 6 and current != "AIzaSy"[:len(current)]:
                if len(current) == 1 and current.upper() == "A":
                    entry.delete(0, tk.END)
                    entry.insert(0, "AIzaSy"[0])
                    return
                entry.delete(0, tk.END)
                if current:
                    entry.insert(0, "AIzaSy")
                return
            
            # For input beyond 'AIzaSy', only allow valid characters
            if len(current) > 6:
                if not re.match(r'^AIzaSy[a-zA-Z0-9_-]*$', current):
                    entry.delete(6, tk.END)
                    return
                    
            # Truncate if exceeds max length
            if len(current) > 39:
                entry.delete(39, tk.END)
                return
        
        # Add real-time validation
        entry.bind('<KeyRelease>', validate_input)
        
        # Wait for dialog
        dialog.wait_window()
        
        new_api_key = result[0]
        if not new_api_key:
            return False
            
        # Show loading message
        loading_window = tk.Toplevel()
        loading_window.title("API Doğrulanıyor")
        loading_window.geometry("300x100")
        loading_window.transient(self.content_frame)
        loading_window.grab_set()
        
        loading_label = tk.Label(loading_window, text="API anahtarı doğrulanıyor...\nLütfen bekleyin...")
        loading_label.pack(pady=20)
        loading_window.update()
        
        try:
            # Validate API key
            is_valid, error_message = self.validate_api_key(new_api_key)
            
            # Close loading window
            loading_window.destroy()
            
            if is_valid:
                self.api_key = new_api_key
                if self.save_api_key(new_api_key):
                    if self.validate_and_initialize_api():
                        messagebox.showinfo("Başarılı", "API anahtarı başarıyla doğrulandı ve kaydedildi.")
                        return True
                    else:
                        raise Exception("API başlatılamadı.")
            else:
                raise Exception(error_message)
                
        except Exception as e:
            loading_window.destroy()
            error_msg = (
                f"API Anahtarı Hatası: {str(e)}\n\n"
                "API anahtarı alabilmek için 'Nasıl Alınır?' butonuna tıklayın."
            )
            if messagebox.askyesno("Hata", error_msg + "\n\nAPI anahtarı alma talimatlarını görmek ister misiniz?"):
                self.show_api_instructions()
            return False
            
        finally:
            if loading_window.winfo_exists():
                loading_window.destroy()

    def create_context_menu(self, widget):
        """Create right-click context menu for text widgets"""
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Kes", command=lambda: self.context_menu_action(widget, "cut"))
        menu.add_command(label="Kopyala", command=lambda: self.context_menu_action(widget, "copy"))
        menu.add_command(label="Yapıştır", command=lambda: self.context_menu_action(widget, "paste"))
        menu.add_separator()
        menu.add_command(label="Tümünü Seç", command=lambda: self.context_menu_action(widget, "select_all"))

        def show_menu(event):
            menu.post(event.x_root, event.y_root)
            
        widget.bind("<Button-3>", show_menu)  # Windows/Linux right click
        return menu

    def context_menu_action(self, widget, action):
        """Handle context menu actions"""
        try:
            if action == "cut":
                widget.event_generate("<<Cut>>")
            elif action == "copy":
                widget.event_generate("<<Copy>>")
            elif action == "paste":
                widget.event_generate("<<Paste>>")
            elif action == "select_all":
                widget.select_range(0, 'end')
        except:
            pass

    def setup_ui(self):
        """Setup the UI components"""
        # Create main frame
        main_frame = ctk.CTkFrame(self.content_frame)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # API and Model frame
        api_frame = ctk.CTkFrame(main_frame)
        api_frame.pack(fill="x", padx=5, pady=5)
        
        # API Key buttons
        api_button = ctk.CTkButton(
            api_frame,
            text="API Anahtarı Ayarla",
            command=self.setup_api_key_dialog
        )
        api_button.pack(side="left", padx=5)
        
        api_help_button = ctk.CTkButton(
            api_frame,
            text="Nasıl Alınır?",
            command=self.show_api_instructions
        )
        api_help_button.pack(side="left", padx=5)

        # Model selection
        model_label = ctk.CTkLabel(api_frame, text="AI Model:")
        model_label.pack(side="left", padx=5)
        
        self.model_var = ctk.StringVar(value=self.current_model if self.current_model else "")
        self.model_dropdown = ctk.CTkOptionMenu(
            api_frame,
            variable=self.model_var,
            values=self.available_models if self.available_models else [""],
            command=self.on_model_change
        )
        self.model_dropdown.pack(side="left", padx=5)

        # Sol taraf - Metin girişi
        self.input_frame = ctk.CTkFrame(main_frame)
        self.input_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        self.input_label = ctk.CTkLabel(self.input_frame, text="Metni buraya girin:")
        self.input_label.pack(pady=5)
        
        self.input_text = scrolledtext.ScrolledText(self.input_frame, wrap=tk.WORD, width=40, height=20)
        self.input_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.create_context_menu(self.input_text)
        
        # Sağ taraf - Sonuçlar
        self.result_frame = ctk.CTkFrame(main_frame)
        self.result_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        
        self.result_label = ctk.CTkLabel(self.result_frame, text="Analiz Sonuçları:")
        self.result_label.pack(pady=5)
        
        self.result_text = scrolledtext.ScrolledText(self.result_frame, wrap=tk.WORD, width=40, height=20)
        self.result_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.result_text.config(state='disabled')
        
        # Butonlar
        self.button_frame = ctk.CTkFrame(main_frame)
        self.button_frame.pack(side="top", fill="x", padx=5, pady=5)
        
        self.analyze_button = ctk.CTkButton(self.button_frame, text="Analiz Et", command=self.start_analysis)
        self.analyze_button.pack(side="left", padx=5)
        
        self.clear_button = ctk.CTkButton(self.button_frame, text="Temizle", command=self.clear_text)
        self.clear_button.pack(side="left", padx=5)

    def load_ai_features(self):
        default_features = {
            'ai_indicators': [
                'olarak bir yapay zeka modeli',
                'kişisel görüş bildiremem',
                'yardımcı olmaya çalışıyorum',
                'sağlanan bilgilere göre',
                'bir dil modeli olarak',
                'nesnellik ve tarafsızlık',
                'etik sınırlar içinde',
                'yasal ve ahlaki standartlara uygun'
            ]
        }
        
        try:
            if os.path.exists(self.ai_features_path):
                with open(self.ai_features_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"AI özellikleri yüklenirken hata: {e}")
        
        return default_features

    def analyze_text(self, text):
        if not self.api_key:
            if not self.setup_api_key_dialog():
                return "API anahtarı gerekli."
        
        try:
            model = genai.GenerativeModel(self.current_model)
            prompt = f"""Aşağıdaki metnin yapay zeka tarafından mı yoksa insan tarafından mı yazıldığını analiz et. 
            Yanıtını şu formatta ver:
            - Sonuç: [Yapay Zeka / İnsan / Belirsiz]
            - Güven Seviyesi: [Düşük / Orta / Yüksek]
            - Nedenler: [Madde madde açıklamalar]

            Metin:
            {text}"""
            
            response = model.generate_content(prompt)
            
            # Handle multi-part responses
            if hasattr(response, 'parts'):
                return ' '.join(part.text for part in response.parts)
            elif hasattr(response, 'candidates') and response.candidates:
                if hasattr(response.candidates[0].content, 'parts'):
                    return ' '.join(part.text for part in response.candidates[0].content.parts)
            
            # Fallback for simple responses
            return str(response)

        except Exception as e:
            if "invalid api key" in str(e).lower():
                self.api_key = None  # Reset invalid API key
                messagebox.showerror("API Hatası", "Geçersiz API anahtarı. Lütfen yeni bir API anahtarı girin.")
                if self.setup_api_key_dialog():
                    return self.analyze_text(text)  # Retry with new API key
            return f"Analiz sırasında hata oluştu: {str(e)}"

    def start_analysis(self):
        if self.is_analyzing:
            self.cancel_analysis = True
            self.analyze_button.configure(text="Analiz Et")
            return

        text = self.input_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Uyarı", "Lütfen analiz edilecek bir metin girin.")
            return

        self.is_analyzing = True
        self.cancel_analysis = False
        self.analyze_button.configure(text="İptal")
        
        self.result_text.config(state='normal')
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", "Analiz yapılıyor...\n")
        self.result_text.config(state='disabled')
        
        self.analysis_thread = threading.Thread(target=self.run_analysis, args=(text,))
        self.analysis_thread.start()

    def run_analysis(self, text):
        try:
            result = self.analyze_text(text)
            if not self.cancel_analysis:
                self.analysis_queue.put(result)
                self.content_frame.after(100, self.update_result)
        except Exception as e:
            self.analysis_queue.put(f"Hata: {str(e)}")
            self.content_frame.after(100, self.update_result)
        finally:
            self.is_analyzing = False
            self.content_frame.after(100, lambda: self.analyze_button.configure(text="Analiz Et"))

    def update_result(self):
        try:
            result = self.analysis_queue.get_nowait()
            self.result_text.config(state='normal')
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert("1.0", result)
            self.result_text.config(state='disabled')
        except queue.Empty:
            pass

    def clear_text(self):
        self.input_text.delete("1.0", tk.END)
        self.result_text.config(state='normal')
        self.result_text.delete("1.0", tk.END)
        self.result_text.config(state='disabled')

    def show(self):
        self.content_frame.pack(fill="both", expand=True)

    def get_available_models(self):
        """Fetch available models directly from Gemini API"""
        try:
            # Get all available models from Gemini API
            models = genai.list_models()
            available_models = []
            
            # Filter for Gemini models and test their availability
            for model in models:
                if 'gemini' in model.name.lower():
                    try:
                        model_instance = genai.GenerativeModel(model.name)
                        response = model_instance.generate_content(
                            "test",
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=1,
                                temperature=0
                            )
                        )
                        available_models.append(model.name)
                        print(f"Model {model.name} is available")
                    except Exception as e:
                        print(f"Model {model.name} is not available: {str(e)}")
                        continue
            
            if not available_models:
                print("No models available, falling back to gemini-pro")
                return ['gemini-pro']
                
            print(f"Available models: {available_models}")
            return available_models
            
        except Exception as e:
            print(f"Error fetching models from API: {str(e)}")
            return ['gemini-pro']  # Fallback to default model

    def start_background_model_validation(self):
        """Start background thread for model validation"""
        validation_thread = threading.Thread(target=self.validate_models_in_background, daemon=True)
        validation_thread.start()

    def validate_models_in_background(self):
        """Validate and update models in background"""
        try:
            # Configure API
            genai.configure(api_key=self.api_key)
            
            # Get models from API
            models = genai.list_models()
            new_models = []
            
            # Filter Gemini models
            for model in models:
                if 'gemini' in model.name.lower():
                    new_models.append(model.name)
            
            if new_models:
                # Update available models
                self.available_models = new_models
                # Update dropdown on main thread
                self.content_frame.after(0, self.update_model_dropdown)
                print("Models updated successfully")
            
        except Exception as e:
            print(f"Background model validation error: {str(e)}")

    def update_model_dropdown(self):
        """Update the model dropdown with new models"""
        if self.model_dropdown and self.model_var:
            current_model = self.model_var.get()
            self.model_dropdown.configure(values=self.available_models)
            # Keep current selection if it's still available
            if current_model in self.available_models:
                self.model_var.set(current_model)
            else:
                self.model_var.set(self.available_models[0])

class AIDetectionApp:
    def __init__(self):
        self.app = ctk.CTk()
        self.app.title("Yapay Zeka Metin Tespit Etme Aracı")
        self.app.geometry("1000x800")
        
        # Ana tema ayarları
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # API key yükleme
        self.config_file = 'config.json'
        self.api_key = self.load_api_key()
        
        if not self.api_key or not self.verify_api_key(self.api_key):
            self.api_key = None
        else:
            # API anahtarını Gemini için ayarla
            genai.configure(api_key=self.api_key)
        
        # Ana içerik frame'i
        self.content_frame = ctk.CTkFrame(self.app)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # AI Detector'ı başlat
        self.ai_detector = AIDetector(self.content_frame)

    def load_api_key(self):
        """Load API key from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config.get('api_key')
        except Exception:
            return None
        return None

    def save_api_key(self, api_key):
        """Save API key to config file"""
        try:
            config = {'api_key': api_key}
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
            return True
        except Exception:
            return False

    def verify_api_key(self, api_key):
        """Verify if the API key is valid"""
        try:
            genai.configure(api_key=api_key)
            genai.list_models()
            return True
        except Exception:
            return False

    def run(self):
        self.app.mainloop()

if __name__ == "__main__":
    app = AIDetectionApp()
    app.run()
