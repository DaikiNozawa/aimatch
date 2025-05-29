import os
import json
import tweepy
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz

# 環境変数から認証情報を取得
X_API_KEY = os.environ['X_API_KEY']
X_API_SECRET = os.environ['X_API_SECRET']
X_ACCESS_TOKEN = os.environ['X_ACCESS_TOKEN']
X_ACCESS_TOKEN_SECRET = os.environ['X_ACCESS_TOKEN_SECRET']
GOOGLE_CREDENTIALS = json.loads(os.environ['GOOGLE_CREDENTIALS'])
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']

# タイムゾーン設定（日本時間）
JST = pytz.timezone('Asia/Tokyo')

def authenticate_twitter():
    """X APIの認証"""
    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET
    )
    return client

def authenticate_google_sheets():
    """Google Sheets APIの認証"""
    credentials = service_account.Credentials.from_service_account_info(
        GOOGLE_CREDENTIALS,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    service = build('sheets', 'v4', credentials=credentials)
    return service

def get_current_time_slot():
    """現在の時間帯を取得（GitHub Actions遅延を考慮）"""
    now = datetime.now(JST)
    weekday = now.weekday()  # 0=月曜日, 6=日曜日
    hour = now.hour
    minute = now.minute
    
    print(f"現在時刻: {now.strftime('%Y/%m/%d %H:%M:%S')} (曜日: {weekday})")
    
    # 平日（月-金）
    if weekday < 5:
        # 朝: 8:00-9:00の範囲で「朝」を許可（±30分）
        if 8 <= hour <= 9 or (hour == 7 and minute >= 30) or (hour == 9 and minute <= 30):
            print("時間帯判定: 朝（平日）")
            return "朝"
        # 昼: 12:00-13:30の範囲で「昼」を許可（±30分〜+60分）
        elif 12 <= hour <= 13 or (hour == 11 and minute >= 30) or (hour == 14 and minute <= 0):
            print("時間帯判定: 昼（平日）")
            return "昼"
        # 夜: 20:00-21:00の範囲で「夜」を許可（±30分）
        elif 20 <= hour <= 21 or (hour == 19 and minute >= 30) or (hour == 21 and minute <= 30):
            print("時間帯判定: 夜（平日）")
            return "夜"
    # 土日
    else:
        # 朝: 10:00-11:00の範囲で「朝」を許可（±30分）
        if 10 <= hour <= 11 or (hour == 9 and minute >= 30) or (hour == 11 and minute <= 30):
            print("時間帯判定: 朝（土日）")
            return "朝"
        # 夜: 20:00-21:00の範囲で「夜」を許可（±30分）
        elif 20 <= hour <= 21 or (hour == 19 and minute >= 30) or (hour == 21 and minute <= 30):
            print("時間帯判定: 夜（土日）")
            return "夜"
    
    print("時間帯判定: 投稿時間外")
    return None

def get_today_theme():
    """曜日別テーマを取得"""
    themes = {
        0: "アプリ比較・選び方",
        1: "プロフィール改善テクニック", 
        2: "メッセージ術",
        3: "デート術",
        4: "体験談・あるある",
        5: "参加型企画",
        6: "振り返り・モチベーション"
    }
    weekday = datetime.now(JST).weekday()
    theme = themes.get(weekday, "")
    print(f"本日のテーマ: {theme}")
    return theme

def get_tweet_from_sheet(service, time_slot, theme):
    """スプレッドシートから投稿内容を取得"""
    try:
        # A列：投稿日時、B列：テーマ、C列：投稿内容、D列：投稿済みフラグ、E列：画像URL（オプション）
        range_name = 'Sheet1!A:E'
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        
        if not values:
            print("❌ スプレッドシートにデータがありません")
            return None, None, None
        
        print(f"✅ スプレッドシートから {len(values)} 行のデータを取得")
        
        # 現在の日付と時間帯
        now = datetime.now(JST)
        today = now.strftime('%Y/%m/%d')
        
        print(f"🔍 検索条件 - 日付: {today}, 時間帯: {time_slot}, テーマ: {theme}")
        
        # 該当する投稿を検索（優先度1: 日付・時間帯・テーマが完全一致）
        for i, row in enumerate(values[1:], start=2):  # ヘッダー行をスキップ
            if len(row) >= 3:
                scheduled_date_str = row[0] if row[0] else ""
                scheduled_theme = row[1] if row[1] else ""
                content = row[2] if row[2] else ""
                is_posted = row[3] if len(row) > 3 else ""
                image_url = row[4] if len(row) > 4 else ""
                
                print(f"行{i}: 日付='{scheduled_date_str}', テーマ='{scheduled_theme}', 投稿済み='{is_posted}'")
                
                # 日付と時間帯の一致を確認（例: "2025/05/28 朝"）
                expected_datetime = f"{today} {time_slot}"
                if (expected_datetime == scheduled_date_str and 
                    scheduled_theme == theme and 
                    is_posted != "済"):
                    print(f"🎯 該当する投稿を発見: 行{i}")
                    print(f"📝 投稿内容: {content[:100]}...")
                    return content, i, image_url
        
        # 予備の投稿を探す（日付指定なし、テーマが一致、未投稿）
        print("⚠️ 日付指定の投稿が見つからないため、予備投稿を検索")
        for i, row in enumerate(values[1:], start=2):
            if len(row) >= 3:
                scheduled_date_str = row[0] if row[0] else ""
                scheduled_theme = row[1] if row[1] else ""
                content = row[2] if row[2] else ""
                is_posted = row[3] if len(row) > 3 else ""
                image_url = row[4] if len(row) > 4 else ""
                
                # 日付指定がない投稿を予備として使用
                if not scheduled_date_str and scheduled_theme == theme and is_posted != "済" and content:
                    print(f"🎯 予備投稿を発見: 行{i}")
                    print(f"📝 投稿内容: {content[:100]}...")
                    return content, i, image_url
        
        print("❌ 該当する投稿が見つかりませんでした")
        return None, None, None
        
    except Exception as e:
        print(f"❌ スプレッドシート読み取りエラー: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def mark_as_posted(service, row_number):
    """投稿済みフラグを更新"""
    try:
        range_name = f'Sheet1!D{row_number}'
        body = {'values': [['済']]}
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        
        # 投稿日時も記録
        timestamp_range = f'Sheet1!F{row_number}'
        timestamp_body = {'values': [[datetime.now(JST).strftime('%Y/%m/%d %H:%M:%S')]]}
        
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=timestamp_range,
            valueInputOption='RAW',
            body=timestamp_body
        ).execute()
        
        print(f"✅ 行{row_number}を投稿済みに更新しました")
        
    except Exception as e:
        print(f"❌ 投稿済みフラグ更新エラー: {e}")

def post_tweet(client, content):
    """ツイートを投稿"""
    try:
        # 改行文字の処理
        content = content.replace('\\n', '\n')
        
        print(f"📤 投稿内容 ({len(content)}文字):")
        print(f"「{content}」")
        
        response = client.create_tweet(text=content)
        return response.data['id']
    except Exception as e:
        print(f"❌ ツイート投稿エラー: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """メイン処理"""
    print("=" * 50)
    print(f"🚀 実行開始: {datetime.now(JST).strftime('%Y/%m/%d %H:%M:%S')}")
    print("=" * 50)
    
    # 現在の時間帯を確認
    time_slot = get_current_time_slot()
    if not time_slot:
        print("⏰ 投稿時間外です")
        print("📋 投稿予定時間:")
        print("  平日: 8:00-9:00, 12:00-13:30, 20:00-21:00")
        print("  土日: 10:00-11:00, 20:00-21:00")
        return
    
    print(f"⏰ 時間帯: {time_slot}")
    
    # 今日のテーマを取得
    theme = get_today_theme()
    
    try:
        # API認証
        print("🔐 API認証中...")
        twitter_client = authenticate_twitter()
        sheets_service = authenticate_google_sheets()
        print("✅ API認証完了")
        
        # スプレッドシートから投稿内容を取得
        tweet_content, row_number, image_url = get_tweet_from_sheet(sheets_service, time_slot, theme)
        
        if not tweet_content:
            print("❌ 投稿する内容が見つかりませんでした")
            print("💡 スプレッドシートの設定を確認してください:")
            print(f"   - 日付: {datetime.now(JST).strftime('%Y/%m/%d')} {time_slot}")
            print(f"   - テーマ: {theme}")
            print("   - 投稿済みフラグが「済」以外であること")
            return
        
        # ツイートを投稿
        tweet_id = post_tweet(twitter_client, tweet_content)
        
        if tweet_id:
            print(f"🎉 投稿成功！ Tweet ID: {tweet_id}")
            print(f"🔗 URL: https://twitter.com/i/web/status/{tweet_id}")
            # 投稿済みフラグを更新
            if row_number:
                mark_as_posted(sheets_service, row_number)
        else:
            print("❌ 投稿に失敗しました")
            
    except Exception as e:
        print(f"❌ 予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("=" * 50)
        print(f"🏁 実行終了: {datetime.now(JST).strftime('%Y/%m/%d %H:%M:%S')}")
        print("=" * 50)

if __name__ == "__main__":
    main()
