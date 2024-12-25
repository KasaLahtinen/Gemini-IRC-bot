# Python IRC Bot

This is a Python script for a basic IRC bot that can connect to an IRC server, join channels, and respond to commands.

**## AI-Assisted Development**

This project was developed with significant assistance from generative AI models, minimizing the amount of human-written code. The following models contributed to various aspects of the project:

*   **Google Gemini:** Provided initial code structure, core IRC functionality, and error handling patterns.
*   **ChatGPT:** Offered suggestions for improvements to code clarity, feature additions, and README generation.
*   **GitHub Copilot:** Assisted with code completion, reducing boilerplate, and suggesting common coding patterns.

While these tools played a key role in the rapid prototyping and development of this bot, the overall design, integration, and final refinement were overseen and validated by human developers.

**## Features**

*   Connects to an IRC server using a YAML configuration file.
*   Handles various IRC messages including PING, JOIN, PRIVMSG, and numeric replies.
*   Supports user-defined commands with basic error handling.
*   Detects and validates URLs in chat messages.
*   Uses `blessed` library for colored terminal output.
*   Handles disconnections and attempts to reconnect automatically.

**## Requirements**

*   Python 3.x
*   Standard Python Libraries: `socket`, `ssl`, `re`, `threading`, `queue`, `traceback`
*   External Libraries:
    *   `chardet`: `pip install chardet`
    *   `validators`: `pip install validators`
    *   `blessed`: `pip install blessed`
    *   `pyyaml`: `pip install pyyaml`
    *   `requests`: `pip install requests`
    *   `psutil`: `pip install psutil`
    *   `bs4`: `pip install BeautifulSoup4`

**## Usage**

1.  Create a configuration file named `config.yaml` in the same directory as your bot script (`bot.py`).
2.  Edit `config.yaml` with your desired settings:

    ```yaml
    bot:
      nickname: your_bot_nickname
      channels:
        - "#channel1"
        - "#channel2"
    connection:
      use_ssl: true  # Set to false to disable SSL
      server: irc.example.com
      port: 6697
      password: your_password  # Optional password for the server
    # thread_pool_size: 4  # Optional thread pool size for channel workers (default 4)
    ```

3.  Run the bot script using:

    ```bash
    python bot.py
    ```

**## Registering Commands**

You can register custom commands for your bot by using the `register_command` function:

```python
def my_command(bot, target, sender, *args):
  # Your command logic here
  pass

Bot.register_command("!mycommand", my_command)
