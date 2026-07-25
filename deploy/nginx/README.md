# nginx deployment configuration

The production nginx reverse proxy must allow request bodies larger than its
1 MB default. Install `upload-limits.conf` under `/etc/nginx/conf.d/` (or add
the directive to the production virtual host), then validate and reload nginx:

```sh
sudo nginx -t
sudo systemctl reload nginx
```

The 25 MB proxy limit leaves room for multipart/form-data overhead above the
application's 20 MB administration-document limit. It applies to all proxied
upload routes, while each application route remains responsible for its own
file-type and size validation.
