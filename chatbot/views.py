from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import auth
from django.contrib.auth.models import User
from .models import Chat
from django.utils import timezone
from django.contrib.auth.decorators import login_required
import os
import json
import uuid
from moviepy.editor import VideoFileClip, concatenate_videoclips
from django.conf import settings
import ast

import g4f

available_gestures = [
    "понять", "вы откуда", "очень", "кто", "хорошо", "когда",
    "где", "делать", "потому что", "ты", "как", "привет",
    "я", "мы", "он", "она", "идти", "любить", "что", "нет",
    "и", "но", "работа", "дом", "сейчас", "здесь", "там",
    "сегодня", "завтра", "почему"
]

def ask_gpt4free(message):
    prompt = (
        "Ты — ассистент, который переводит текст на русский жестовый язык, используя ограниченное количество жестов. "
        "У тебя есть только следующие видеофайлы с жестами:\n\n"
        + "\n".join(f"- {g}.mp4" for g in available_gestures) +
        "\n\nЕсли точных соответствий жестам нет, **постарайся передать общий смысл фразы**, используя только доступные жесты. "
        "Допускается упрощение или перефразирование, но **использовать можно только приведённые выше жесты**. "
        "Не добавляй пояснений. Ответ должен быть **строго в виде списка файлов .mp4**, в том порядке, в котором их нужно склеить.\n\n"
        "Пример ответа:\n['привет.mp4', 'ты.mp4', 'как.mp4']\n\n"
        f"Входная фраза: {message}"
    )

    response = g4f.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Ты полезный переводчик с русского на видео-жесты."},
            {"role": "user", "content": prompt}
        ]
    )
    return response

def generate_video_clip(sequence, output_filename):
    clips = []
    missing = []

    for filename in sequence:
        path = os.path.join(settings.BASE_DIR, 'media', 'gestures', filename)
        if os.path.exists(path):
            try:
                clips.append(VideoFileClip(path))
            except Exception as e:
                print(f"[moviepy error] Ошибка при загрузке {filename}: {e}")
        else:
            print(f"[not found] Файл не найден: {path}")
            missing.append(filename)

    if clips:
        try:
            final = concatenate_videoclips(clips)
            output_path = os.path.join(settings.MEDIA_ROOT, 'outputs', output_filename)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            final.write_videofile(output_path, codec="libx264", audio=False)
            print(f"[success] Видео сохранено: {output_path}")
            return f"/media/outputs/{output_filename}"
        except Exception as e:
            print(f"[moviepy error] Ошибка при склейке видео: {e}")
    else:
        print(f"[fail] Нет клипов для склейки. Возможно, отсутствуют файлы: {missing}")
    return None

@login_required(login_url='login')
def chatbot(request):
    chats = Chat.objects.filter(user=request.user)

    if request.method == 'POST':
        message = request.POST.get('message')
        raw_response = ask_gpt4free(message)
        print(f"[gpt raw response] {raw_response}")

        # Пытаемся привести строку к списку, если ответ — строка
        try:
            cleaned = raw_response.strip().split('\n')[0]
            sequence = ast.literal_eval(cleaned)
            if not isinstance(sequence, list):
                raise ValueError("Не список")
        except Exception as e:
            print(f"[parse error] Невозможно разобрать ответ: {e}")
            sequence = []

        # Генерируем уникальное имя файла
        filename = f"user_{request.user.id}_{uuid.uuid4().hex[:8]}.mp4"
        video_url = generate_video_clip(sequence, filename)

        # Сохраняем как текстовый ответ JSON + ссылка
        # response_text = f"{sequence}\n\n<video controls width='320'><source src='{video_url}' type='video/mp4'></video>" if video_url else str(sequence)

        response_text = f"<video controls width='320'><source src='{video_url}' type='video/mp4'></video>" if video_url else "Не удалось создать видео."

        chat = Chat(
            user=request.user,
            message=message,
            response=response_text,
            created_at=timezone.now()
        )
        chat.save()
        return JsonResponse({'message': message, 'response': response_text})
    return render(request, 'chatbot.html', {'chats': chats})

def login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = auth.authenticate(request, username=username, password=password)
        if user is not None:
            auth.login(request, user)
            return redirect('chatbot')
        else:
            error_message = 'Invalid username or password'
            return render(request, 'login.html', {'error_message': error_message})
    else:
        return render(request, 'login.html')

def register(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password1 = request.POST['password1']
        password2 = request.POST['password2']

        if password1 == password2:
            try:
                user = User.objects.create_user(username, email, password1)
                user.save()
                auth.login(request, user)
                return redirect('chatbot')
            except:
                error_message = 'Error creating account'
                return render(request, 'register.html', {'error_message': error_message})
        else:
            error_message = 'Passwords do not match'
            return render(request, 'register.html', {'error_message': error_message})
    return render(request, 'register.html')

def logout(request):
    auth.logout(request)
    return redirect('login')
