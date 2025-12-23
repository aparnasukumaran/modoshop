from django.shortcuts import render,redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from .decorators import admin_required
from .models import Product, Category,Order,Payment, CartItem,Wishlist,GST,OrderItem, ContactMessage
from django.contrib import messages
from django.utils.text import slugify
from django.shortcuts import render, redirect, get_object_or_404
from .models import UserProfile
from django.db.models.signals import post_save
from django.dispatch import receiver
from .forms import UserForm, UserProfileForm
import stripe
from django.urls import reverse
from django.conf import settings
stripe.api_key = settings.STRIPE_SECRET_KEY
from django.utils import timezone
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.core.mail import send_mail
from django.utils.timezone import make_aware
from datetime import datetime





def login_page(request):
    if request.method == "POST":
        username = request.POST.get("username") 
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            if user.is_superuser:
                messages.success(request, "Welcome Admin! Welcome to Admin Panel...")
                return redirect('admin_dashboard')  

            messages.success(request, "Login successful! Welcome back.")
            return redirect('home')

        else:
            messages.error(request, "Invalid username or password")

    return render(request, "login.html")


def register_page(request):
    if request.method == "POST":
        username = request.POST.get("username")
        gender = request.POST.get('gender')
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match")
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return redirect('register')

        user = User.objects.create_user(username=username, email=email, password=password1)
        user.profile.gender = gender
        user.save()
        messages.success(request, "Account created successfully! Please login.")
        return redirect('login')

    return render(request, "register.html")

def logout_page(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('login')

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
# ___________________User___________________________________

def home(request):
    categories = Category.objects.all()
    return render(request, 'shop/home.html',{'categories':categories})

def shop_view(request):
    products = Product.objects.all()
    categories = Category.objects.all()

    search_query = request.GET.get('search', '')
    category_id = request.GET.get('category', '')

    if request.user.is_authenticated:
        wishlist_ids = list(
            Wishlist.objects.filter(user=request.user)
            .values_list('product_id', flat=True)
        )
    else:
        wishlist_ids = []

    if search_query:
        products = products.filter(name__icontains=search_query)

    if category_id:
        products = products.filter(category_id=category_id)

    products = products.order_by('?')

    # AJAX request
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        html = render(
            request,
            'shop/partials/product_cards.html',
            {
                'products': products,
                'wishlist_ids': wishlist_ids
            }
        ).content.decode('utf-8')
        return JsonResponse({'html': html})

    return render(request, 'shop/shop.html', {
        'products': products,
        'categories': categories,
        'wishlist_ids': wishlist_ids
    })

# ___________________profile___________________________________

def about_view(request):
    return render(request, 'shop/about.html')

def contact_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        phone = request.POST.get('phone')

        ContactMessage.objects.create(
            name=name,
            email=email,
            message=message,
            phone=phone
        )

        messages.success(request, "Your message has been sent!")
        return redirect('home')

    return render(request, "shop/contact.html")
# ___________________profile___________________________________

@login_required
def profile_page(request):
    return render(request, "shop/profile.html")

@login_required
def edit_profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        user_form = UserForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()  
            return redirect('profile_page')
    else:
        user_form = UserForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    return render(request, 'shop/edit_profile.html', context)


# ___________________wishlist___________________________________
@login_required
def wishlist_page(request):
    items = Wishlist.objects.filter(user=request.user)
    return render(request, 'shop/wishlist.html', {"items": items})

@login_required
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    wishlist_item, created = Wishlist.objects.get_or_create(
        user=request.user, product=product
    )

    if created:
        messages.success(request, f"'{product.name}' added to your wishlist!")
    else:
        wishlist_item.delete()
        messages.info(request, f"'{product.name}' removed from your wishlist!")

    return redirect(request.META.get("HTTP_REFERER", "shop_home"))
# ___________________order___________________________________
@login_required
def orders(request):
    orders = (
        Order.objects
        .filter(user=request.user,is_deleted_by_user=False)
        .prefetch_related('items__product')
        .order_by('-created_at')
    )
    return render(request, 'shop/orders.html',{ 'orders': orders})

@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status == "Pending":
        order.status = "Cancelled"
        order.save()
        messages.success(request, f'Order #{order.id} has been cancelled successfully.')
    else:
        messages.warning(request, f'Order #{order.id} cannot be cancelled.')

    return redirect('orders')

@login_required
def user_delete_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    order.is_deleted_by_user = True
    order.save()

    messages.success(request, "Order removed from your view.")
    return redirect('orders')



def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    products = category.products.all()
    if request.user.is_authenticated:
        wishlist_ids = Wishlist.objects.filter(user=request.user).values_list('product_id', flat=True)
    else:
        wishlist_ids = []
    return render(request, 'shop/category_detail.html', {'category': category, "wishlist_ids": list(wishlist_ids),})

# ___________________products___________________________________

def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug)

    is_wishlisted = False
    if request.user.is_authenticated:
        is_wishlisted = Wishlist.objects.filter(
            user=request.user, product=product
        ).exists()

    return render(request, "shop/product_detail.html", {
        "product": product,
        "is_wishlisted": is_wishlisted,
    })

# ___________________cart___________________________________
@login_required
def cart_page(request):
    items = CartItem.objects.filter(user=request.user)
    total_amount = sum(item.total_price for item in items)
    return render(request, 'shop/cart.html', {'items': items, 'total_amount': total_amount})

@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart_item, created = CartItem.objects.get_or_create(user=request.user, product=product)

    if not created:
        cart_item.quantity += 1
        cart_item.save()
        messages.success(request, f"Quantity of '{product.name}' increased in your cart.")
    else:
        messages.success(request, f"'{product.name}' added to your cart.")

    return redirect('cart_page')

@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, user=request.user)
    product_name = item.product.name
    item.delete()
    messages.success(request, f"'{product_name}' has been removed from your cart.")
    return redirect('cart_page')

@login_required
def increase_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, user=request.user)
    item.quantity += 1
    item.save()
    return redirect('cart_page')

# Decrease quantity
@login_required
def decrease_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, user=request.user)
    if item.quantity > 1:
        item.quantity -= 1
        item.save()
    else:
        item.delete()
    return redirect('cart_page')


# ___________________checkout___________________________________
@login_required
def update_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, user=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'increase':
            item.quantity += 1
        elif action == 'decrease' and item.quantity > 1:
            item.quantity -= 1
        item.save()

    return redirect('checkout')

@login_required
def checkout_view(request):
    items = CartItem.objects.filter(user=request.user)
    if not items.exists():
        return redirect('cart_page')

    subtotal = sum(item.total_price for item in items)
    gst = GST.objects.first()
    gst_percent = gst.percent if gst else 0
    gst_amount = subtotal * gst_percent / 100
    total_amount = subtotal + gst_amount

    if request.method == 'POST':
        address = request.POST.get('address', '')
        payment_method = request.POST.get('payment_method', 'COD')

        # cod
        if payment_method == 'COD':
            order = Order.objects.create(
                user=request.user,
                payment_method='COD',
                status='Pending',
                total_price=total_amount,
                address=address
            )

            Payment.objects.create(
                order=order,
                method='Cash',
                amount=total_amount,
                is_paid=False
            )

            for item in items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity
                )

            items.delete()


            # Send email
            subject = f"Order Confirmation - #{order.id}"
            message = f"Hi {request.user.username},\n\n" \
              f"Thank you for your order! Your order ID is {order.id}.\n" \
              f"Total Amount: ₹{total_amount:.2f}\n" \
              f"Payment Method: COD\n" \
              f"Address: {address}\n\n" \
              f"We will notify you once your order is shipped.\n\n" \
              f"Thanks,\nShop Team"

            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email],fail_silently=False)

            return redirect('order_success', order_id=order.id)

   
        elif payment_method == 'ONLINE':
            address = request.POST.get('address')
            request.session['checkout_address'] = address
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'inr',
                        'product_data': {
                            'name': f'Order #{request.user.id}',
                        },
                        'unit_amount': int(total_amount * 100),
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=request.build_absolute_uri(
                    reverse('stripe_success')
                ),
                cancel_url=request.build_absolute_uri(
                    reverse('checkout')
                ),
            )

            return redirect(session.url)

    context = {
        'items': items,
        'subtotal': subtotal,
        'gst_amount': gst_amount,
        'total_amount': total_amount,
        'gst_percent': gst_percent,
    }
    return render(request, 'shop/checkout.html', context)


@login_required
def stripe_success(request):
    items = CartItem.objects.filter(user=request.user)
    address = request.session.pop('checkout_address', '')

    subtotal = sum(item.total_price for item in items)
    gst = GST.objects.first()
    gst_percent = gst.percent if gst else 0
    gst_amount = subtotal * gst_percent / 100
    total_amount = subtotal + gst_amount

    order = Order.objects.create(
        user=request.user,
        payment_method='ONLINE',
        status='Pending',
        total_price=total_amount,
        address=address
    )
    Payment.objects.create(
        order=order,
        method='Card',
        amount=total_amount,
        is_paid=True,
    )


    for item in items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity
        )

    items.delete()

    subject = f"Order Confirmation - #{order.id}"
    message = f"Hi {request.user.username},\n\n" \
          f"Your online payment for order #{order.id} of ₹{total_amount:.2f} has been received.\n" \
          f"Payment Method: Card\n" \
          f"Address: {address}\n\n" \
          f"Thanks for shopping with us!\nShop Team"

    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email],fail_silently=False)

    return redirect('order_success', order_id=order.id)

@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'shop/order_success.html', {'order': order})


@login_required
def buy_now(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    

    subtotal = product.get_price()
    gst = GST.objects.first()
    gst_percent = gst.percent if gst else 0
    gst_amount = subtotal * gst_percent / 100
    total_amount = subtotal + gst_amount

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'COD')
        address = request.POST.get('address', '') 

        # Stripe Checkout
        if payment_method == 'ONLINE':
            request.session['checkout_address'] = address

            stripe.api_key = settings.STRIPE_SECRET_KEY

            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'inr',
                        'product_data': {'name': product.name},
                        'unit_amount': int(total_amount * 100),
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=request.build_absolute_uri(
                    reverse('buy_now_success', kwargs={'product_id': product.id})
                ),
                cancel_url=request.build_absolute_uri(
                    reverse('checkout')
                ),
            )
            return redirect(session.url)

        # Cash on Delivery
        else:
            order = Order.objects.create(
                user=request.user,
                payment_method='COD',
                total_price=total_amount,
                address=address
            )
            OrderItem.objects.create(order=order, product=product, quantity=1)

            Payment.objects.create(
                order=order,
                method='Cash',
               amount=total_amount,
               is_paid=False 
            )


            subject = f"Order Confirmation - #{order.id}"
            message = (
                f"Hi {request.user.username},\n\n"
                f"Thank you for your order! Your order ID is {order.id}.\n"
                f"Total Amount: ₹{total_amount:.2f}\n"
                f"Payment Method: COD\n"
                f"Address: {address}\n\n"
                f"We will notify you once your order is shipped.\n\n"
                f"Thanks,\nShop Team"
            )

            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email])
            
            return redirect('order_success', order_id=order.id)

    context = {
        'items': [{'product': product, 'quantity': 1, 'total_price': subtotal}],
        'subtotal': subtotal,
        'gst_amount': gst_amount,
        'total_amount': total_amount,
        'gst_percent': gst_percent,
        'buy_now': True,  
    }
    return render(request, 'shop/checkout.html', context)

@login_required
def buy_now_success(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    address = request.session.pop('checkout_address', '')


    subtotal = product.get_price()
    gst = GST.objects.first()
    gst_percent = gst.percent if gst else 0
    gst_amount = subtotal * gst_percent / 100
    total_amount = subtotal + gst_amount

    order = Order.objects.create(
        user=request.user,
        payment_method='ONLINE',
        status='Pending',
        total_price=total_amount,
        address=address
    )
    OrderItem.objects.create(order=order, product=product, quantity=1)
    Payment.objects.create(
       order=order,
       method='Card', 
       amount=total_amount,
       is_paid=True,   
       paid_at=timezone.now() 
    )

    subject = f"Order Confirmation - #{order.id}"
    message = f"Hi {request.user.username},\n\n" \
          f"Your online payment for order #{order.id} of ₹{total_amount:.2f} has been received.\n" \
          f"Payment Method: Card\n" \
          f"Address: {address}\n\n" \
          f"Thanks for shopping with us!\nShop Team"

    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email],fail_silently=False)


    return redirect('order_success', order_id=order.id)


# ______________Admin________________________________________

@admin_required
def admin_dashboard(request):
    products_count = Product.objects.count()
    categories_count = Category.objects.count()
    orders_count = Order.objects.filter(is_deleted=False).count()
    payments_count = Payment.objects.filter(is_deleted=False).count()
    gst_count = GST.objects.count()
    messages_count = ContactMessage.objects.count()

    recent_orders = (
        Order.objects
        .filter(is_deleted=False)
        .select_related('user')
        .prefetch_related('items__product')
        .order_by('-id')[:5]
    )

    recent_payments = (
       Payment.objects
       .filter(is_deleted=False)
       .select_related('order__user')       
       .prefetch_related('order__items__product') 
       .order_by('-id')[:5]               
    )

    return render(request, 'admin/admin_dashboard.html', {
        'products_count': products_count,
        'categories_count': categories_count,
        'orders_count': orders_count,
        'payments_count': payments_count,
        'recent_orders': recent_orders,
        'recent_payments': recent_payments,
        'gst_count': gst_count,
        'messages_count' : messages_count
    })


@admin_required
def products_page(request):
    products = Product.objects.all()
    return render(request, 'admin/products.html', {'products': products})

@admin_required
def categories_page(request):
    categories = Category.objects.all()
    return render(request, 'admin/categories.html', {'categories': categories})

@admin_required
def orders_page(request):
    orders = Order.objects.filter(is_deleted=False).order_by('-id').prefetch_related('items__product').all()
    for order in orders:
        order.total_quantity = sum(item.quantity for item in order.items.all())

    return render(request, 'admin/orders.html', {'orders': orders})

@admin_required
def mark_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    if order.status != 'Delivered':
        order.status = 'Delivered'
        order.save()

        subject = f"Your Order #{order.id} Has Been Delivered"
        message = (
            f"Hi {order.user.username},\n\n"
            f"Good news! Your order #{order.id} has been successfully delivered.\n\n"
            f"Thank you for shopping with us!\n"
            f"Shop Team"
        )

        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [order.user.email])

        messages.success(request, f"Order #{order.id} marked as Delivered and email sent to user.")
    else:
        messages.info(request, f"Order #{order.id} is already delivered.")

    return redirect('orders_page')

@admin_required
def delete_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.is_deleted = True
    order.status = "Deleted by Admin"
    order.save()

    messages.success(request, f"Order #{order.id} deleted successfully.")
    return redirect('orders_page')

# ________________________________Payment_______________________________________
@admin_required
def payments_page(request):
    payments = Payment.objects.filter(is_deleted=False).all()
    return render(request, 'admin/payments.html', {'payments': payments})

@admin_required
def remove_payment(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    payment.is_deleted = True 
    payment.save()
    messages.success(request, f"Payment #{payment.id} removed successfully.")
    return redirect('payments_page')

# _______________________________gst_______________________________________
@admin_required
def list_gst(request):
    gsts = GST.objects.all() 
    return render(request, "admin/gst_list.html", {"gsts": gsts})

@admin_required
def add_edit_gst(request, id=None):
    if id:
        gst = get_object_or_404(GST, id=id)
    else:
        gst = None

    if request.method == "POST":
        name = request.POST.get("name")
        percent = request.POST.get("percent")

        if gst:
            gst.name = name
            gst.percent = percent
            gst.save()
        else:
            GST.objects.create(name=name, percent=percent)

        return redirect("gst_list")

    return render(request, "admin/gst_form.html", {"gst": gst})


@admin_required
def delete_gst(request, id):
    gst = GST.objects.get(id=id)
    gst.delete()
    return redirect("gst_list")

@admin_required
def add_product(request, product_id=None):
    categories = Category.objects.all()
    gst_list = GST.objects.all()

    if product_id:
        product = get_object_or_404(Product, id=product_id)
    else:
        product = None

    if request.method == "POST":
        name = request.POST.get('name')
        category_id = request.POST.get('category')
        category = get_object_or_404(Category, id=category_id)
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        image = request.FILES.get('image')
        description = request.POST.get("description")
        offer_price = request.POST.get("offer_price") or None
        gst_id = request.POST.get("gst")

        if product:
            product.name = name
            product.category = category
            product.price = price
            product.stock = stock
            product.description = description
            product.offer_price = offer_price

            if image:
                product.image = image

            product.save()
            messages.success(request, "Product updated successfully!")
        else:
            Product.objects.create(
                name=name,
                category=category,
                price=price,
                stock=stock,
                description=description,
                offer_price=offer_price,
                image=image,
            )
            messages.success(request, "Product added successfully!")

        return redirect('products_page')

    return render(request, 'admin/add_product.html', {
        'categories': categories,
        'product': product,
        'gst_list': gst_list,
    })

@admin_required
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.delete()
    messages.success(request, "Product deleted successfully!")
    return redirect('products_page')


@admin_required
def add_category(request, category_id=None):
    category = None
    if category_id:
        category = get_object_or_404(Category, id=category_id)

    if request.method == "POST":
        name = request.POST.get('name')
        image = request.FILES.get('image')

        if category: 
            category.name = name
            if image:
                category.image = image
            category.slug = slugify(name)
            category.save()
            messages.success(request, "Category updated successfully!")
        else: 
            Category.objects.create(
                name=name,
                slug=slugify(name),
                image=image
            )
            messages.success(request, "Category added successfully!")

        return redirect('categories_page')

    return render(request, 'admin/add_category.html', {'category': category})


@admin_required
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.delete()
    messages.success(request, "Category deleted successfully!")
    return redirect('categories_page')

# ______________________message________________________________
@admin_required
def admin_messages_view(request):
    messages_list = ContactMessage.objects.all().order_by('-created_at')
    return render(request, 'admin/admin_messages.html', {'messages_list': messages_list})

@admin_required
def delete_message(request, msg_id):
    ContactMessage.objects.filter(id=msg_id).delete()
    messages.success(request, "Message deleted successfully!")
    return redirect('admin_messages')

# ___________________report___________________________________
@admin_required
def admin_reports(request):
    filter_type = request.GET.get('filter', 'orders')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    if from_date:
        from_date = make_aware(datetime.strptime(from_date, "%Y-%m-%d"))
    if to_date:
        to_date = make_aware(datetime.strptime(to_date, "%Y-%m-%d"))

    if filter_type == 'orders':
        data = Order.objects.all().select_related('payment').order_by('-created_at')

        if from_date:
            data = data.filter(created_at__gte=from_date)
        if to_date:
            data = data.filter(created_at__lte=to_date)

    elif filter_type == 'payments':
        data = Payment.objects.all()

        if from_date:
            data = data.filter(paid_at__gte=from_date)
        if to_date:
            data = data.filter(paid_at__lte=to_date)

    elif filter_type == 'users':
        data = User.objects.all().order_by('-date_joined')

        if from_date:
            data = data.filter(date_joined__gte=from_date)
        if to_date:
            data = data.filter(date_joined__lte=to_date)

    elif filter_type == 'products':
        data = Product.objects.all()

    elif filter_type == 'categories':
        data = Category.objects.all()

    else:
        data = []

    context = {
        'filter': filter_type,
        'data': data,
        'from_date': request.GET.get('from_date', ''),
        'to_date': request.GET.get('to_date', ''),
    }

    return render(request, "admin/admin_reports.html", context)

# ___________________policy___________________________________
def privacy_policy(request):
    return render(request, 'policy_template.html', {'page_title': 'Privacy Policy'})

def terms_of_service(request):
    return render(request, 'policy_template.html', {'page_title': 'Terms of Service'})