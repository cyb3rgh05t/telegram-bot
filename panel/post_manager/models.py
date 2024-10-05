from django.db import models

class Post(models.Model):
    content = models.TextField()
    image = models.ImageField(upload_to='images/', null=True, blank=True)
    topic_id = models.CharField(max_length=255, default='-1001234567890')

    def __str__(self):
        return self.content
