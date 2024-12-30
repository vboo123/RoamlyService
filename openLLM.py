from gpt4all import GPT4All
import sys


def draw_cat():
    model = GPT4All(model_name='Meta-Llama-3-8B-Instruct.Q4_0.gguf', allow_download=False)
    tokens = []
    for token in model.generate("In the following text, how many times am I using the word architectural: Can you provide a lively, narrative-style history of Hollywood Sign with engaging storytelling, fun facts, recent events, and tourist-friendly tips, especially tailored for an audience from United States of America who is interested in Drawing, Running, and Acting? Include references to popular culture from that country or region to help engage them more. Keep it casual, friendly, and informative, and write in a way that's easy to read out loud. The story should touch on the cost or financial history behind Rodeo Drive, architectural details, key political or social events that shaped its history, and information about who owns it now and how it is maintained or managed—all woven into one flowing, easy-to-read narrative without headers, bullet points, or sections. This should be tailored to a young audience and medium length response.", streaming=True):
        tokens.append(token)
        sys.stdout.write(token)

    sys.stdout.flush()


if __name__ == '__main__':
    draw_cat()

