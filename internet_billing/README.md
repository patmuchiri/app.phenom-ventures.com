Created custom permission mixins:

AdminRequiredMixin - For Administrator-only access

ManagerOrAccountantRequiredMixin - For Manager/Accountant access

StaffRequiredMixin - For Support Staff/Network Technician access

Implemented role-based permissions:

Administrator has full access to all features

Manager and Accountant can view all clients, add new clients, record payments, send bulk SMS, view reports and transactions

Support Staff and Network Technician can only view all clients and active clients

Protected sensitive actions:

Client creation/modification restricted to Managers/Accountants

Bulk SMS restricted to Administrators/Managers

Financial reports restricted to Administrators/Managers/Accountants

User management restricted to Administrators only

Simplified views where possible while maintaining all functionality

Added proper permission checks on all sensitive actions

Maintained all existing features while adding the new permission structure
