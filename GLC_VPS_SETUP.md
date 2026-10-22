# Putting the GLC server on a Hetzner VPS

This guide puts your GLC server on a Hetzner VPS running Ubuntu 24.04.
Wherever you see `YOUR_IP`, put your server's IPv4 address from the Hetzner panel.

---

## Part 1 – Pack the folder (on your PC)

1. **Stop the server** if it's running: press Ctrl+C in its PowerShell window.

2. **Pack the folder.** Open **PowerShell** and paste these three lines:

   ```powershell
   cd $HOME\Desktop
   tar -czf glc-ptcgo.tar.gz --exclude=GLC-PTCGO/venv --exclude=GLC-PTCGO/ven --exclude=GLC-PTCGO/spirit/assets/bundleCache --exclude=GLC-PTCGO/spirit/assets/cards --exclude=__pycache__ --exclude=client_errors.log --exclude=*.bak GLC-PTCGO
   (Get-Item glc-ptcgo.tar.gz).Length / 1MB
   ```

   This creates `glc-ptcgo.tar.gz` on your Desktop. The last line shows its size in MB; it should be around 100–300 MB.
   It leaves out the Windows `venv`, and also the card art and compiled card files. The server downloads and rebuilds those itself, which is much faster than uploading several GB from home.

3. **Upload it to the server.** Type `yes` if you're asked whether to trust the server, then enter the root password Hetzner emailed you:

   ```powershell
   scp glc-ptcgo.tar.gz root@YOUR_IP:/opt/
   ```

---

## Part 2 – Set up the server

4. **Log in to the server:**

   ```powershell
   ssh root@YOUR_IP
   ```

   Hetzner may ask you to change the password the first time. Pick a strong one and keep it safe.

5. **Tell the server its own address.** Change `YOUR_IP` here, then paste it:

   ```bash
   IP=YOUR_IP
   ```

6. **Install updates and the tools the server needs.** This takes a few minutes:

   ```bash
   apt update && apt upgrade -y
   apt install -y python3-venv python3-pip nginx ufw
   ```

   If a pink or purple screen asks which services to restart, just press Enter.

7. **Add 4 GB of swap.** This is extra memory, so the first start doesn't run out:

   ```bash
   fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
   echo '/swapfile none swap sw 0 0' >> /etc/fstab
   ```

8. **Open only the ports the game needs:**

   ```bash
   ufw allow OpenSSH && ufw allow 8000/tcp && ufw allow 39389/tcp && ufw --force enable
   ```

9. **Unpack the server and install Python packages:**

   ```bash
   cd /opt && tar -xzf glc-ptcgo.tar.gz && mv GLC-PTCGO glc-ptcgo && cd glc-ptcgo
   python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
   ```

10. **Download the card art.** This only fetches GLC cards and can take 10–30 minutes:

    ```bash
    PYTHONPATH=/opt/glc-ptcgo ./venv/bin/python -m spirit.tools.install_recent_card_art
    ```

    If it ends by listing failed downloads, run the same command again. It only fetches what's missing.

11. **Set up nginx.** It handles the large card downloads reliably:

    ```bash
    cp deploy/nginx-spirit.conf /etc/nginx/sites-available/glc
    ln -s /etc/nginx/sites-available/glc /etc/nginx/sites-enabled/glc
    mkdir -p /var/cache/spirit_assets && chown www-data:www-data /var/cache/spirit_assets
    nginx -t && systemctl reload nginx
    ```

    `nginx -t` should say `syntax is ok` and `test is successful`.

12. **Make the server start by itself.** This also restarts it automatically if the VPS reboots. Paste the whole block:

    ```bash
    cat > /etc/systemd/system/glc.service <<EOF
    [Unit]
    Description=GLC PTCGO server
    After=network-online.target
    Wants=network-online.target

    [Service]
    WorkingDirectory=/opt/glc-ptcgo
    Environment=PYTHONPATH=/opt/glc-ptcgo
    Environment=SPIRIT_HTTP_PORT=8001
    Environment=MALLOC_ARENA_MAX=2
    Environment=SPIRIT_PUBLIC_HOST=$IP
    ExecStart=/opt/glc-ptcgo/venv/bin/python -m spirit.main
    Restart=on-failure
    RestartSec=5
    TimeoutStartSec=0

    [Install]
    WantedBy=multi-user.target
    EOF
    systemctl daemon-reload && systemctl enable --now glc
    ```

13. **Watch it start:**

    ```bash
    journalctl -u glc -f
    ```

    The first start builds all the card files, which can take 20–60 minutes on a CX23.
    It's ready when you see **`[TCP] Server listening`**. Press Ctrl+C to stop watching; the server keeps running.

---

## Part 3 – Connect the game

14. **Point your game at the server.** On each PC, open `Pokemon Trading Card Game Online_Data\cake.cfg` in the game folder and change these three lines:

    ```ini
    hostname=YOUR_IP
    versionURL=http://YOUR_IP:8000/
    assetURL=http://YOUR_IP:8000/
    ```

    Leave everything else in the file as it is.

15. **Log in.** Your existing accounts came across with the database, so use the same username and password as before. A new player can type any username and password, and the account is created on their first login.
    The first login downloads the card files, so give it a few minutes.

16. **Check the admin page:** open `http://YOUR_IP:8000/admin` and log in as `pokeron`.

---

## Useful commands later

Run these on the server after `ssh root@YOUR_IP`:

| What | Command |
|---|---|
| See the live log | `journalctl -u glc -f` |
| Restart the server | `systemctl restart glc` |
| Stop / start | `systemctl stop glc` / `systemctl start glc` |
| After changing card art or the landing image | `rm -rf /var/cache/spirit_assets/* && systemctl restart glc` |

## If something goes wrong

- **The game can't connect:** check `cake.cfg` uses the right IP. Then run `systemctl status glc` and look for `active (running)`.
- **Login works, then drops straight away:** `SPIRIT_PUBLIC_HOST` is wrong. Edit `/etc/systemd/system/glc.service`, then run `systemctl daemon-reload && systemctl restart glc`.
- **Cards show as blank:** re-run step 10, then `systemctl restart glc`.
