from django.db import models

class Post(models.Model):
    content = models.TextField()
    image = models.ImageField(upload_to='images/', null=True, blank=True)  # New field for image

    def __str__(self):
        return self.content
