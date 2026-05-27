RECIPES = {
    "ร้านขนม/นางรอง - เริ่มต้น": [
        '#ร้านขนมเมืองนางรอง OR "ร้านขนมเมืองนางรอง" -is:retweet lang:th',
        '"ของกินนางรอง" OR "คาเฟ่นางรอง" -is:retweet lang:th',
        '"ขนมของฝาก" OR "ของฝากนางรอง" -is:retweet lang:th',
    ],
    "หา Lead คนกำลังถาม": [
        '"แนะนำร้านขนม" OR "ร้านขนมอร่อย" OR "ร้านไหนดี" -is:retweet lang:th',
        '"ขอพิกัด" OR "ซื้อที่ไหน" OR "สั่งขนม" -is:retweet lang:th',
    ],
    "Pain Point / คนบ่น": [
        '"ส่งช้า" OR "รอนาน" OR "แพง" OR "ไม่อร่อย" OR "หาไม่เจอ" -is:retweet lang:th',
    ],
    "Creator / รีวิวอาหาร": [
        '"รีวิว" "ของกิน" -is:retweet lang:th',
        '"คาเฟ่" OR "ร้านขนม" OR "ขนมของฝาก" -is:retweet lang:th',
    ],
    "สล็อต/พนัน - หาโพสต์คนจริง ไม่เอาโปรโมท": [
        '"สล็อต" ("โดนโกง" OR "ถอนเงินไม่ได้" OR "เลิกเล่น" OR "เสียหมด" OR "ติดพนัน" OR "เตือนภัย") -is:retweet lang:th',
    ],
}


def recipe_names():
    return list(RECIPES.keys())
