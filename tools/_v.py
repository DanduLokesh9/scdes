from app import module_one as m1
s = m1.by_number("00")
print("step 00:", s.title, "| asks:", s.asks, "| questions:", len(s.questions))
s1 = m1.by_number("01")
print("step 01:", s1.title, "| asks:", s1.asks, "| questions:", len(s1.questions))