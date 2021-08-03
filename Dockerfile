FROM mcr.microsoft.com/playwright:focal

WORKDIR /app

COPY . .
RUN pip install -r requirements.txt
RUN python -m playwright install

CMD [ "python", "primelooter.py --loop" ]