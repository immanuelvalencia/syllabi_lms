import re

with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update body
content = content.replace('x-data="{ sidebarOpen: false }"', 'x-data="{ sidebarOpen: false, sidebarExpanded: false }"')

# 2. Update main container
content = content.replace('<div class="lg:pl-72 flex flex-col h-full">', '<div class="lg:pl-20 flex flex-col h-full transition-all duration-300">')

# 3. Desktop sidebar replacement
old_sidebar = """    <!-- Static sidebar for desktop -->
    <div class="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-72 lg:flex-col border-r border-gray-200 bg-white">
      <div class="flex grow flex-col gap-y-5 overflow-y-auto px-6 pb-4">
        <div class="flex h-16 shrink-0 items-center mt-2">
          <a href="{% url 'academics:dashboard' %}" class="flex items-center gap-3 text-green-600 font-bold text-2xl">
            <div class="w-10 h-10 rounded-xl bg-green-600 text-white flex items-center justify-center shadow-md shadow-green-600/30">
              <i class="bi bi-mortarboard-fill text-xl"></i>
            </div>
            Syllabi
          </a>
        </div>
        <nav class="flex flex-1 flex-col mt-4">
          <ul role="list" class="flex flex-1 flex-col gap-y-7">
            <li>
              <div class="text-xs font-semibold leading-6 text-gray-400 mb-2 uppercase tracking-wider">Main Navigation</div>
              <ul role="list" class="-mx-2 space-y-1">
                {% if profile.role == "instructor" %}
                    <li><a href="{% url 'academics:instructor_dashboard' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold"><i class="bi bi-speedometer2 text-gray-400 group-hover:text-green-600 text-lg shrink-0"></i> Dashboard</a></li>
                    <li><a href="{% url 'academics:teacher_courses' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold"><i class="bi bi-journal-bookmark text-gray-400 group-hover:text-green-600 text-lg shrink-0"></i> Courses</a></li>
                {% elif profile.role == "student" %}
                    <li><a href="{% url 'academics:student_dashboard' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold"><i class="bi bi-speedometer2 text-gray-400 group-hover:text-green-600 text-lg shrink-0"></i> Dashboard</a></li>
                {% else %}
                    <li><a href="{% url 'academics:academic_admin_dashboard' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold"><i class="bi bi-speedometer2 text-gray-400 group-hover:text-green-600 text-lg shrink-0"></i> Dashboard</a></li>
                    <li><a href="/admin/" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold"><i class="bi bi-gear text-gray-400 group-hover:text-green-600 text-lg shrink-0"></i> System Admin</a></li>
                {% endif %}
              </ul>
            </li>
            
            <li class="mt-auto">
              <form action="{% url 'logout' %}" method="post">
                {% csrf_token %}
                <button type="submit" class="hover:bg-gray-50 hover:text-red-600 text-gray-700 group flex w-full gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                  <i class="bi bi-box-arrow-right text-gray-400 group-hover:text-red-600 text-lg shrink-0"></i> Sign out
                </button>
              </form>
            </li>
          </ul>
        </nav>
      </div>
    </div>"""

new_sidebar = """    <!-- Static sidebar for desktop -->
    <div class="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:flex-col border-r border-gray-200 bg-white transition-all duration-300 overflow-x-hidden"
         :class="sidebarExpanded ? 'w-72 shadow-xl' : 'w-20'"
         @mouseenter="sidebarExpanded = true"
         @mouseleave="sidebarExpanded = false">
      <div class="flex grow flex-col gap-y-5 overflow-y-auto px-4 pb-4">
        <div class="flex h-16 shrink-0 items-center mt-2 px-1">
          <a href="{% url 'academics:dashboard' %}" class="flex items-center gap-4 text-green-600 font-bold text-2xl whitespace-nowrap">
            <div class="w-10 h-10 shrink-0 rounded-xl bg-green-600 text-white flex items-center justify-center shadow-md shadow-green-600/30">
              <i class="bi bi-mortarboard-fill text-xl"></i>
            </div>
            <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">Syllabi</span>
          </a>
        </div>
        <nav class="flex flex-1 flex-col mt-4">
          <ul role="list" class="flex flex-1 flex-col gap-y-7">
            <li>
              <div class="text-xs font-semibold leading-6 text-gray-400 mb-2 uppercase tracking-wider transition-all duration-300 whitespace-nowrap" :class="sidebarExpanded ? 'opacity-100 px-2' : 'opacity-0 w-0 h-0 overflow-hidden m-0 p-0'">Main Nav</div>
              <ul role="list" class="space-y-1">
                {% if profile.role == "instructor" %}
                    <li><a href="{% url 'academics:instructor_dashboard' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex items-center gap-x-4 rounded-md p-2 text-sm leading-6 font-semibold whitespace-nowrap"><i class="bi bi-speedometer2 text-gray-400 group-hover:text-green-600 text-xl shrink-0 w-6 text-center"></i> <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">Dashboard</span></a></li>
                    <li><a href="{% url 'academics:teacher_courses' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex items-center gap-x-4 rounded-md p-2 text-sm leading-6 font-semibold whitespace-nowrap"><i class="bi bi-journal-bookmark text-gray-400 group-hover:text-green-600 text-xl shrink-0 w-6 text-center"></i> <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">Courses</span></a></li>
                {% elif profile.role == "student" %}
                    <li><a href="{% url 'academics:student_dashboard' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex items-center gap-x-4 rounded-md p-2 text-sm leading-6 font-semibold whitespace-nowrap"><i class="bi bi-speedometer2 text-gray-400 group-hover:text-green-600 text-xl shrink-0 w-6 text-center"></i> <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">Dashboard</span></a></li>
                {% else %}
                    <li><a href="{% url 'academics:academic_admin_dashboard' %}" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex items-center gap-x-4 rounded-md p-2 text-sm leading-6 font-semibold whitespace-nowrap"><i class="bi bi-speedometer2 text-gray-400 group-hover:text-green-600 text-xl shrink-0 w-6 text-center"></i> <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">Dashboard</span></a></li>
                    <li><a href="/admin/" class="hover:bg-gray-50 hover:text-green-600 text-gray-700 group flex items-center gap-x-4 rounded-md p-2 text-sm leading-6 font-semibold whitespace-nowrap"><i class="bi bi-gear text-gray-400 group-hover:text-green-600 text-xl shrink-0 w-6 text-center"></i> <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">System Admin</span></a></li>
                {% endif %}
              </ul>
            </li>
            
            <li class="mt-auto">
              <form action="{% url 'logout' %}" method="post">
                {% csrf_token %}
                <button type="submit" class="hover:bg-gray-50 hover:text-red-600 text-gray-700 group flex items-center w-full gap-x-4 rounded-md p-2 text-sm leading-6 font-semibold whitespace-nowrap">
                  <i class="bi bi-box-arrow-right text-gray-400 group-hover:text-red-600 text-xl shrink-0 w-6 text-center"></i> <span class="transition-opacity duration-300" :class="sidebarExpanded ? 'opacity-100' : 'opacity-0'">Sign out</span>
                </button>
              </form>
            </li>
          </ul>
        </nav>
      </div>
    </div>"""

if old_sidebar in content:
    content = content.replace(old_sidebar, new_sidebar)
    with open('templates/base.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully replaced.")
else:
    print("Old sidebar not found. Revert needed?")
