# Шаблоны атрибутов для подрас
SUBRACE_ATTRIBUTES = {
    1: { #Человек/Норд
        "strength": 20,
        "agility": 20,
        "intelligence": 10,
        "endurance": 10,

        "health": 10,
        "energy": 10,
        "mana": 0,
        "stamina": 10,

        "charisma": 0,
        "luck": 10
    },
    2: { #Человек/ Ост
        "strength": 10,
        "agility": 30,
        "intelligence": 20,
        "endurance": 0,

        "health": 5,
        "energy": 5,
        "mana": 5,
        "stamina": 20,

        "charisma": 5,
        "luck": 10
    },
    3: { #Человек/Ориентал
        "strength": 10,
        "agility": 20,
        "intelligence": 10,
        "endurance": 20,

        "health": 0,
        "energy": 10,
        "mana": 0,
        "stamina": 10,

        "charisma": 0,
        "luck": 30
    },
    4: {  # Эльф/Лесной
        "strength": 0,
        "agility": 30,
        "intelligence": 20,
        "endurance": 0,

        "health": 5,
        "energy": 10,
        "mana": 0,
        "stamina": 5,

        "charisma": 20,
        "luck": 10
    },
    5: {  # Эльф - Темный
        "strength": 15,
        "agility": 15,
        "intelligence": 15,
        "endurance": 15,

        "health": 0,
        "energy": 10,
        "mana": 10,
        "stamina": 5,

        "charisma": 0,
        "luck": 15
    },
    6: {  # Эльф - Малах
        "strength": 5,
        "agility": 15,
        "intelligence": 20,
        "endurance": 10,

        "health": 0,
        "energy": 0,
        "mana": 10,
        "stamina": 10,

        "charisma": 10,
        "luck": 20
    },
    7: {  # Драконид/Равагарт
        "strength": 30,
        "agility": 0,
        "intelligence": 0,
        "endurance": 30,

        "health": 20,
        "energy": 10,
        "mana": 0,
        "stamina": 10,

        "charisma": 0,
        "luck": 0
    },
    8: {  # Драконид/Рорис
        "strength": 10,
        "agility": 30,
        "intelligence": 10,
        "endurance": 10,

        "health": 10,
        "energy": 5,
        "mana": 5,
        "stamina": 0,

        "charisma": 0,
        "luck": 20
    },
    9: {  # Дворф/Золотой
        "strength": 20,
        "agility": 0,
        "intelligence": 20,
        "endurance": 10,

        "health": 20,
        "energy": 20,
        "mana": 5,
        "stamina": 5,

        "charisma": 0,
        "luck": 0
    },
    10: {  # Дворф/Ониксовый
        "strength": 20,
        "agility": 0,
        "intelligence": 20,
        "endurance": 10,

        "health": 20,
        "energy": 20,
        "mana": 5,
        "stamina": 5,

        "charisma": 0,
        "luck": 0
    },
    11: {  # Демон/Левиаан
        "strength": 30,
        "agility": 20,
        "intelligence": 0,
        "endurance": 0,

        "health": 10,
        "energy": 10,
        "mana": 0,
        "stamina": 10,

        "charisma": 0,
        "luck": 20
    },
    12: {  # Демон/Альб
        "strength": 0,
        "agility": 20,
        "intelligence": 40,
        "endurance": 0,

        "health": 0,
        "energy": 20,
        "mana": 20,
        "stamina": 0,

        "charisma": 0,
        "luck": 0
    },
    13: {  # Бистмен/Зверолюд
        "strength": 20,
        "agility": 20,
        "intelligence": 0,
        "endurance": 20,

        "health": 5,
        "energy": 10,
        "mana": 10,
        "stamina": 5,

        "charisma": 0,
        "luck": 10
    },
    14: {  # Бистмен/Полукровка
        "strength": 0,
        "agility": 40,
        "intelligence": 10,
        "endurance": 10,

        "health": 5,
        "energy": 10,
        "mana": 0,
        "stamina": 5,

        "charisma": 10,
        "luck": 10
    },
    15: {  # Урук - северные
        "strength": 40,
        "agility": 10,
        "intelligence": 0,
        "endurance": 30,

        "health": 10,
        "energy": 5,
        "mana": 0,
        "stamina": 5,

        "charisma": 0,
        "luck": 0
    },
    16: {  # Урук/Темный урук
        "strength": 30,
        "agility": 20,
        "intelligence": 0,
        "endurance": 20,

        "health": 10,
        "energy": 10,
        "mana": 0,
        "stamina": 0,

        "charisma": 0,
        "luck": 10
    },
}



CLASS_ITEMS = {
    1: [  # Стартовая экипировка для Воина
        {"item_id": 1, "quantity": 1},  # Меч
        {"item_id": 2, "quantity": 1},  # Щит
    ],
    2: [  # Стартовая экипировка для Ловкача
        {"item_id": 3, "quantity": 2},  # Лук
        {"item_id": 4, "quantity": 10}, # Стрелы
    ],
    3: [  # Стартовая экипировка для Мага
        {"item_id": 5, "quantity": 5},  # Зелье здоровья
    ]
}

