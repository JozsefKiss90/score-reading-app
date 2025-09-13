import mido
print(mido.get_input_names())
with mido.open_input("SE61 0") as port:
    print("Listening on SE61 0 ...")
    for msg in port:
        print(msg)


