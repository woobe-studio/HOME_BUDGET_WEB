import csv
import json

from django.contrib.auth.models import User
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from scripts.custom_scripts import *
from scripts.custom_classes import *
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UpdateUserForm, UpdateProfileForm, WalletForm
from .models import BalanceChange, Category, Wallet

def home(request):
    return render(request, 'users/home.html')

@login_required
def profile(request):
    if request.method == 'POST':
        user_form = UpdateUserForm(request.POST, instance=request.user)
        profile_form = UpdateProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile is updated successfully')
            return redirect(to='users-profile')
    else:
        user_form = UpdateUserForm(instance=request.user)
        profile_form = UpdateProfileForm(instance=request.user.profile)
    return render(request, 'users/profile.html', {'user_form': user_form, 'profile_form': profile_form})


@login_required
def wallet_selection(request):
    profile = request.user.profile
    wallets = Wallet.objects.filter(profiles__in=[request.user.profile])
    return render(request, 'users/wallet_selection.html', {'wallets': wallets})


@login_required
def create_wallet(request):
    if request.method == 'POST':
        profile = request.user.profile
        name = request.POST.get('wallet_name')
        currency = request.POST.get('currency')
        wallet_type = request.POST.get('wallet_type')

        existing_wallet = Wallet.objects.filter(name=name, profiles__in=[profile]).first()
        if existing_wallet:
            messages.error(request, 'A wallet with this name already exists.')
            return redirect('users-wallet_selection')

        new_wallet = Wallet.objects.create(name=name, currency=currency, wallet_type=wallet_type)
        new_wallet.profiles.add(profile)

        if wallet_type == 'group':
            user_emails = request.POST.getlist('users')
            for email in user_emails:
                try:
                    user = User.objects.get(email=email)
                    user_profile = user.profile
                    new_wallet.profiles.add(user_profile)
                except User.DoesNotExist:
                    messages.warning(request, f'User with email {email} does not exist.')

        categories = ['Entertainment', 'Food', 'Transportation', 'Health', 'Shopping', 'Savings']
        categories.sort()
        for category_name in categories:
            category_obj, created = Category.objects.get_or_create(name=category_name)
            new_wallet.categories.add(category_obj)
        categories = sorted(new_wallet.categories.all(), key=lambda c: c.name.lower())
        wallet_id = new_wallet.id
        messages.success(request, 'Wallet created successfully.')

        return render(request, 'users/wallet.html', {
            'wallet_id': wallet_id,
            'balance': '0.00',
            'currency': currency,
            'categories': categories,
        })

@login_required
def select_existing_wallet(request):
    if request.method == 'POST':
        wallet_id = request.POST.get('existing_wallet')
        # Perform any actions needed with the selected wallet ID
        # For example, you could redirect to a page specific to the selected wallet
        return redirect('users-wallet', wallet_id=wallet_id)
    else:
        # Handle GET request if needed
        pass

@login_required
def wallet(request, wallet_id):
    profile = request.user.profile
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    form = WalletForm()
    if request.method == 'POST':
        form = WalletForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data.get('amount')
            description = form.cleaned_data.get('description')
            category = form.cleaned_data.get('category')
            new_category = form.cleaned_data.get('new_category')
            if new_category:
                category_obj, created = Category.objects.get_or_create(name=new_category)
                wallet.categories.add(category_obj)
            elif category:
                category_obj = category
                wallet.categories.add(category_obj)
            else:
                messages.error(request, 'No category was selected')
                return redirect('users-wallet', wallet_id=wallet_id)
            if amount != Decimal('0'):
                if amount < Decimal('0'):
                    if wallet.balance >= abs(amount):
                        wallet.balance += amount
                        wallet.save()
                        BalanceChange.objects.create(wallet=wallet, amount=amount, description=description, category=category_obj)
                        messages.success(request, f'Balance updated successfully: ${amount:.2f} | Category: {category_obj.name} | Description: {description}')
                    else:
                        messages.error(request, 'Insufficient balance for the transaction')
                else:
                    wallet.balance += amount
                    wallet.save()
                    BalanceChange.objects.create(wallet=wallet, amount=amount, description=description, category=category_obj)
                    messages.success(request, f'Balance updated successfully: ${amount:.2f} | Category: {category_obj.name} | Description: {description}')
            else:
                messages.error(request, 'Amount must be non-zero to update the balance')
            return redirect('users-wallet', wallet_id=wallet_id)
    formatted_balance = f'{wallet.balance:.2f}'
    currency = wallet.currency
    categories = sorted(wallet.categories.all(), key=lambda c: c.name.lower())
    return render(request, 'users/wallet.html', {'form': form, 'balance': formatted_balance, 'currency': currency, 'categories': categories, 'wallet_id': wallet_id})

@login_required
def clear_categories(request, wallet_id):
    profile = request.user.profile
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    wallet.categories.clear()
    default_categories = ['Entertainment', 'Food', 'Transportation', 'Health', 'Shopping', 'Savings']
    default_categories.sort()
    for category_name in default_categories:
        category_obj, created = Category.objects.get_or_create(name=category_name)
        wallet.categories.add(category_obj)
    messages.success(request, "All categories have been cleared and default categories have been added.")
    return redirect('users-wallet', wallet_id=wallet_id)

@login_required
def balance_changes(request, wallet_id):
    profile = request.user.profile
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    sort_by = request.GET.get('sort_by')
    selected_category = request.GET.get('selected_category')
    min_amount = request.GET.get('min_amount')
    max_amount = request.GET.get('max_amount')
    day = request.GET.get('day')
    day_name = request.GET.get('day_name')
    month_name = request.GET.get('month')
    year = request.GET.get('year')

    try:
        min_amount = Decimal(min_amount) if min_amount else None
    except (InvalidOperation, ValueError):
        min_amount = None

    try:
        max_amount = Decimal(max_amount) if max_amount else None
    except (InvalidOperation, ValueError):
        max_amount = None

    try:
        day = int(day) if day else None
    except (ValueError, TypeError):
        day = None

    try:
        month = get_months().get(month_name) if month_name else None
    except AttributeError:
        month = None

    try:
        year = int(year) if year else None
    except (ValueError, TypeError):
        year = None

    years = get_years()
    months = list(get_months().keys())
    days = get_days(datetime.now().year, month)
    day_names = get_day_names()

    try:
        day_name_week = (day_names.index(day_name) + 2 ) % 7
    except ValueError:
        day_name_week = None

    sorted_changes = BalanceChange.objects.filter(wallet=wallet)

    category_filter_display = 'block'
    amount_filter_display = 'block'
    date_filter_display = 'block'
    if selected_category and selected_category != "None":
        category = get_object_or_404(Category, name=selected_category)
        sorted_changes = sorted_changes.filter(category=category)
    if min_amount is not None:
        sorted_changes = sorted_changes.filter(amount__gte=min_amount)
    if max_amount is not None:
        sorted_changes = sorted_changes.filter(amount__lte=max_amount)
    if year is not None:
        sorted_changes = sorted_changes.filter(timestamp__year=year)
    if month is not None:
        sorted_changes = sorted_changes.filter(timestamp__month=month)
    if day_name_week is not None:
        sorted_changes = sorted_changes.filter(timestamp__week_day=day_name_week)
    if day is not None:
        sorted_changes = sorted_changes.filter(timestamp__day=day)
    if sort_by == 'AscendingCost':
        balance_changes = sorted_changes.order_by('amount')
    elif sort_by == 'DescendingCost':
        balance_changes = sorted_changes.order_by('-amount')
    elif sort_by == 'DateOldestFirst':
        balance_changes = sorted_changes.order_by('timestamp')
    elif sort_by == 'DateNewestFirst':
        balance_changes = sorted_changes.order_by('-timestamp')
    elif sort_by == 'AscendingCategoryName':
        balance_changes = sorted_changes.order_by('category__name')
    elif sort_by == 'DescendingCategoryName':
        balance_changes = sorted_changes.order_by('-category__name')
    else:
        balance_changes = sorted_changes.order_by('-timestamp')
        sort_by = 'SelectSort'

    paginator = Paginator(balance_changes, 3)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    currency = wallet.currency
    categories = sorted(wallet.categories.all(), key=lambda c: c.name.lower())
    return render(request, 'users/balance_changes.html', {
        'wallet_id': wallet_id,
        'page_obj': page_obj,
        'sort_by': sort_by,
        'selected_category': selected_category,
        'categories': categories,
        'currency': currency,
        'min_amount': min_amount,
        'max_amount': max_amount,
        'category_filter_display': category_filter_display,
        'amount_filter_display': amount_filter_display,
        'date_filter_display': date_filter_display,
        'years': years,
        'months': months,
        'days': days,
        'day_names': day_names,
        'year': str(year),
        'month': month_name,
        'day': str(day),
        'day_name': day_name,
    })

@login_required
def clear_balance_changes(request, wallet_id):
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    BalanceChange.objects.filter(wallet=wallet).delete()
    messages.success(request, "All balance change history has been cleared.")
    return redirect('users-balance_changes', wallet_id=wallet_id)

@login_required
def edit_balance_change(request, wallet_id):
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    if request.method == 'POST':
        edit_id = request.POST.get('edit-id')
        edit_description = request.POST.get('edit-description')
        edit_category = request.POST.get('edit-category')
        try:
            balance_change = BalanceChange.objects.get(id=edit_id, wallet=wallet)
            if edit_description:
                balance_change.description = edit_description
            if edit_category:
                category = Category.objects.get(name=edit_category)
                balance_change.category = category

            balance_change.save()
            messages.success(request, "Balance Change has been edited successfully.")
        except BalanceChange.DoesNotExist:
            messages.error(request, "Balance Change not found.")
        except Category.DoesNotExist:
            messages.error(request, "Category not found.")
        except InvalidOperation:
            messages.error(request, "Invalid amount entered.")

        return redirect('users-balance_changes', wallet_id=wallet_id)

@login_required
def delete_balance_change(request, wallet_id):
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    if request.method == 'POST':
        delete_id = request.POST.get('delete-id')
        try:
            balance_change = BalanceChange.objects.get(id=delete_id, wallet=wallet)
            deleted_amount = balance_change.amount
            balance_change.delete()
            wallet.balance -= deleted_amount
            wallet.save()
            messages.success(request, "Balance Change has been deleted successfully.")
        except BalanceChange.DoesNotExist:
            messages.error(request, "Balance Change not found.")

        return redirect('users-balance_changes', wallet_id=wallet_id)


@login_required
def export_balance_changes(request, wallet_id):
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    balance_changes = BalanceChange.objects.filter(wallet=wallet)

    if request.method == 'POST':
        export_format = request.POST.get('export_format', 'pdf')
        sort_by = request.POST.get('sort_by', None)
        selected_category = request.POST.get('selected_category', None)
        min_amount = request.POST.get('min_amount', None)
        max_amount = request.POST.get('max_amount', None)
        year = request.POST.get('year', None)
        month = request.POST.get('month', None)
        day = request.POST.get('day', None)
        day_name = request.POST.get('day_name', None)

        day_names = get_day_names()
        try:
            day_name_week = (day_names.index(day_name) + 2) % 7
        except ValueError:
            day_name_week = None

        if selected_category:
            balance_changes = balance_changes.filter(category__name=selected_category)
        if min_amount:
            balance_changes = balance_changes.filter(amount__gte=min_amount)
        if max_amount:
            balance_changes = balance_changes.filter(amount__lte=max_amount)
        if year:
            balance_changes = balance_changes.filter(timestamp__year=year)
        if month:
            balance_changes = balance_changes.filter(timestamp__month=month)
        if day:
            balance_changes = balance_changes.filter(timestamp__day=day)
        if day_name:
            balance_changes = balance_changes.filter(timestamp__week_day=day_name_week)

        if export_format == 'pdf':
            pdf_filename = "balance_changes_report.pdf"
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'

            doc = SimpleDocTemplate(response, pagesize=letter)
            table_data = [['Time', 'Description', 'Amount', 'Category']]

            for change in balance_changes:
                table_data.append([
                    change.timestamp.strftime("%b %d, %Y %I:%M %p"),
                    change.description,
                    "${:.2f}".format(change.amount),
                    change.category.name
                ])

            table = Table(table_data)

            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ])

            table.setStyle(style)
            doc.build([table])

            return response

        elif export_format == 'csv':
            csv_filename = "balance_changes_report.csv"
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{csv_filename}"'

            writer = csv.writer(response)
            writer.writerow(['Time', 'Description', 'Amount', 'Category'])

            for change in balance_changes:
                writer.writerow([
                    change.timestamp.strftime("%b %d, %Y %I:%M %p"),
                    change.description,
                    "${:.2f}".format(change.amount),
                    change.category.name
                ])

            return response

    return redirect('users-balance_changes', wallet_id=wallet_id)

@login_required
def charts(request, wallet_id):
    wallet = get_object_or_404(Wallet, id=wallet_id, profiles__in=[request.user.profile])
    balance_changes = BalanceChange.objects.filter(wallet=wallet)

    income_data = [0] * 12
    expense_data = [0] * 12

    for change in balance_changes:
        month_index = change.timestamp.month - 1
        if change.amount > 0:
            income_data[month_index] += change.amount
        else:
            expense_data[month_index] += abs(change.amount)

    months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]

    data = {
        'months': months,
        'income_data': income_data,
        'expense_data': expense_data,
    }

    serialized_data = json.dumps(data, cls=DjangoJSONEncoder)

    return render(request, 'users/charts.html', {'data': serialized_data, 'wallet_id': wallet_id})
