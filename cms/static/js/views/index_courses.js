function indexCourses(){
    var course = "";
    course = document.URL.split("/")[4];
    var url = window.location.host + "/index";
    $.ajax({
        type: "POST",
        url: url,
        data: {"course": course},
        success: success
    });
}

function success(){
    console.log("Success!");
}

$(document).ready(function() {
    $("#index-courses").unbind();
    $("#index-courses").eq(0).bind("click", indexCourses);
});